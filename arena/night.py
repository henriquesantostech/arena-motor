"""The night: fetch data, check it, fill orders, value portfolios, decide and write the journal.

process_day() is a pure function: same stored data + same state = same package.
"""
import copy
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

import pandas as pd

from . import config, sources
from .agents import decide
from .archive import fingerprint
from .checks import check
from .market import apply_events, fill_pending, new_participant, sell, value
from .signals import compute, market_ok
from .view import View


# --- code version ------------------------------------------------------------------
def code_version():
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha[:12]
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.ENGINE_DIR, capture_output=True,
                             text=True, check=True).stdout.strip()[:12]
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "arena", "rules"], cwd=config.ENGINE_DIR,
                               capture_output=True, text=True).stdout.strip()
        return sha + ("+modified" if dirty else "")
    except Exception:
        return "unknown"


# --- fetch data ----------------------------------------------------------------------
def fetch(archive, now=None, history_from=None):
    """Appends new data to the archive. Returns a summary (counts only)."""
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fetched_at = now_utc.strftime("%Y-%m-%dT%H:%M:%S")
    end = sources.last_closed_day(now_utc)
    p = archive.read("prices")
    if history_from:
        start = history_from
    elif len(p):
        start = (pd.Timestamp(p["date"].max()) - pd.Timedelta(days=10)).date().isoformat()
    else:
        raise RuntimeError("archive has no history: run 'create' first")
    tickers = config.universe_tickers() + config.INDICES
    prices, events = sources.prices_and_events(tickers, start, end)
    n_p = archive.append("prices", prices, fetched_at)
    n_e = archive.append("events", events, fetched_at)
    f = archive.read("fx")
    fx_start = history_from or ((pd.Timestamp(f["date"].max()) - pd.Timedelta(days=10)).date().isoformat() if len(f) else start)
    fx = sources.fx_rates(fx_start)
    fx = fx[fx["date"] <= end]
    n_f = archive.append("fx", fx, fetched_at)
    n_t = _tiingo_sample(archive, end, fetched_at)
    return {"until": end, "prices": n_p, "events": n_e, "fx": n_f, "tiingo": n_t}


def _tiingo_sample(archive, day, fetched_at, n=5):
    if not os.environ.get("TIINGO_KEY"):
        return 0
    t = archive.read("tiingo")
    if len(t) and (t["date"] == day).any():
        return 0
    univ = sorted(config.universe_tickers())
    seed = int(hashlib.sha256(day.encode()).hexdigest()[:8], 16)
    sample = [univ[(seed + i * 17) % len(univ)] for i in range(n)]
    rows = []
    for tk in sample:
        c = sources.crosscheck_close(tk, day)
        if c is not None:
            rows.append({"date": day, "ticker": tk, "close": c})
    return archive.append("tiingo", pd.DataFrame(rows), fetched_at) if rows else 0


# --- days to process -----------------------------------------------------------------
def days_to_process(archive, until=None):
    cfg = archive.cfg
    p = archive.read("prices")
    days = sorted(p.loc[p["ticker"] == config.INDEX_PRICE, "date"].unique().tolist())
    done = archive.journal_days()
    last = done[-1] if done else None
    f = archive.read("fx")
    first_fx = f["date"].min() if len(f) else "9999"
    out = [d for d in days if d >= cfg["day_zero"] and (last is None or d > last) and d >= first_fx]
    if until:
        out = [d for d in out if d <= until]
    # If many companies are missing on a day, the data is still incomplete: wait for the next night.
    univ = set(config.universe_tickers())
    counts = p[p["date"].isin(out) & p["ticker"].isin(univ)].groupby("date")["ticker"].nunique()
    complete = []
    for d in out:
        if counts.get(d, 0) < 0.9 * len(univ):
            break
        complete.append(d)
    return complete


def previous_journal_day(archive, day):
    done = [d for d in archive.journal_days() if d < day]
    return done[-1] if done else None


def current_cutoff(archive):
    """How far the fetched data goes (date and time of the last fetch)."""
    return max((archive.read(n)["fetched_at"].max() for n in ("prices", "events", "fx", "tiingo")
                if len(archive.read(n))), default="")


def apply_dna_updates(state, day):
    """Rule changes to the DNA take effect on their date for participants alive then (logged in the journal)."""
    population = {p["name"]: p for p in config.POPULATION["participants"]}
    applied = []
    for u in config.RULES.get("dna_updates", []):
        if u["effective_from"] > day:
            continue
        for name, part in state["participants"].items():
            dna, src = part.get("dna"), population.get(name, {}).get("dna")
            if not dna or not src:
                continue
            new = {f: src[f] for f in u["fields"] if f not in dna and f in src}
            if new:
                dna.update(new)
                applied.append({"participant": name, "rules_version": u["version"], "fields": new})
    return applied


# --- process one day -------------------------------------------------------------------
def process_day(archive, day, prev_state, cutoff=None):
    cutoff = cutoff or current_cutoff(archive)
    view = View(archive, day, cutoff)
    if not view.is_trading_day(day):
        raise RuntimeError(f"{day} is not a trading day in the archive")
    rate = view.rate(day)
    universe = config.universe_tickers()

    if prev_state is None:
        state = {"date": day, "participants": {}, "missing_days": {}, "delisted": {}}
        for p in config.POPULATION["participants"]:
            state["participants"][p["name"]] = new_participant(p, day)
        prev_fp = None
    else:
        prev_fp = fingerprint(prev_state)
        state = copy.deepcopy(prev_state)
        state["date"] = day
    rule_changes = apply_dna_updates(state, day) if prev_state is not None else []

    decisions = {}
    events_today = view.events_on(day)
    for name, part in state["participants"].items():
        d = {"events": [], "fills": [], "cancelled": []}
        if prev_state is not None:
            part["days"] += 1
            d["events"] = apply_events(part, events_today, rate)
            d["fills"], d["cancelled"] = fill_pending(part, view, day, rate)
        decisions[name] = d

    # Delistings: N trading days in a row without data -> forced sale at the last price
    today = view.tickers_on(day)
    limit = config.DATA["missing_days_for_delisting"]
    for t in universe:
        if t in state["delisted"]:
            continue
        if t in today:
            state["missing_days"].pop(t, None)
            continue
        state["missing_days"][t] = state["missing_days"].get(t, 0) + 1
        if state["missing_days"][t] >= limit:
            state["delisted"][t] = day
            state["missing_days"].pop(t, None)
            price = view.last_close(t)
            for name, part in state["participants"].items():
                part["pending"] = [o for o in part["pending"] if o["ticker"] != t]
                if t in part["positions"] and price:
                    r = sell(part, t, part["positions"][t]["shares"], price, rate, day)
                    if r:
                        r["reason"] = {"cause": "delisting",
                                       "text": f"Forced sale: {t} has had no quote for {limit} trading days (delisted), at the last known price."}
                        decisions[name]["fills"].append(r)
    state["missing_days"] = dict(sorted(state["missing_days"].items()))

    values = {n: value(p, view, day, rate) for n, p in state["participants"].items()}

    excluded, crosschecked = check(view, universe, state["delisted"])
    eligible = [t for t in universe if t not in state["delisted"] and t not in excluded]
    raw, z = compute(view, eligible)
    ok, sp, ma = market_ok(view)

    for name, part in state["participants"].items():
        part["pending"] = decide(part, day, view, rate, values[name], z, raw, excluded, state["delisted"], ok)

    signals_tab = {t: {"z": {s: float(z.loc[t, s]) for s in config.PRICE_SIGNALS},
                       "raw": {s: (None if pd.isna(raw.loc[t, s]) else float(raw.loc[t, s]))
                               for s in config.PRICE_SIGNALS}}
                   for t in z.index}
    package = {
        "date": day,
        "mode": archive.cfg.get("mode", "trial"),
        "version": {"engine": config.ENGINE_VERSION, "rules": config.RULES_VERSION, "code": code_version()},
        "inputs": {"cutoff": cutoff, **view.fingerprints(), "previous_state": prev_fp},
        "market": {"eurusd": rate, "sp500": sp, "sp500_ma200": ma, "above_ma": ok},
        "checks": {"excluded": excluded, "tiingo": crosschecked, "companies_with_signals": int(len(z))},
        "signals": signals_tab,
        "decisions": decisions,
        "values": values,
        "state": state,
    }
    if rule_changes:   # only on the nights a rule change takes effect
        package["rule_changes"] = rule_changes
    return package


def process(archive, until=None, on_done=None):
    done = []
    for day in days_to_process(archive, until):
        prev = previous_journal_day(archive, day)
        state = archive.read_journal(prev)["state"] if prev else None
        package = process_day(archive, day, state)
        archive.write_journal(day, package)
        done.append(day)
        if on_done:
            on_done(day, package)
    return done


# --- replay a night ----------------------------------------------------------------------
def replay(archive, day):
    stored = archive.read_journal(day)
    if stored is None:
        raise RuntimeError(f"no journal for {day}")
    prev = previous_journal_day(archive, day)
    state = archive.read_journal(prev)["state"] if prev else None
    new = process_day(archive, day, state, stored["inputs"]["cutoff"])
    new = json.loads(json.dumps(new, ensure_ascii=False))
    a, b = dict(stored), dict(new)
    code_a = a.pop("version", {}).get("code")
    code_b = b.pop("version", {}).get("code")
    differences = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    return {"day": day, "identical": not differences, "differences": differences,
            "stored_code": code_a, "current_code": code_b}
