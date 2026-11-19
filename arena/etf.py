"""ETF League: the second league of the Arena. Fictional money, euros, UCITS ETFs, monthly rotation.

Simulation only: no broker, no real orders, no advice. It reuses the engine's pieces: the Yahoo adapter, the
private archive (a sub-folder `etf/`), the night run, the Signal Lab maths (Newey-West), the merit statistics
(PSR, DSR, MinTRL), and the monkeys idea (random portfolios with the same rotation as the strategies).

Rules: rules/etf.json (frozen universe, costs, tax, band, strategies). Pre-registered signals: rules/etf_signals.json.

Timing (same as the engine): decisions at the close of the last trading day of each month (and once at day zero);
orders fill at the next open, sells first. Costs: 0.1% commission plus half a spread per fill. Tax: 28% on net
realised gains per calendar year, shown apart (value before tax, and value after tax).

Everything is recomputed from the raw prices every night (deterministic); nothing is stored but the results:
  etf/league.json          day zero of the live league (created once)
  etf/raw/prices.csv       date,ticker,open,high,low,close,volume,fetched_at   (append-only)
  etf/live/values.csv      date, one column per participant (value in EUR at the close, before tax)
  etf/live/monkeys.csv     date, p05, p50, p95 and best of the 1,000 monkeys
  etf/rehearsal/...        the same on past data from rehearsal_start to day zero: TECHNICAL REHEARSAL, never evidence
  etf/report.json         statistics, ranking against the World ETF and the monkeys, verdict
  etf/signals.csv          shadow signals (append-only) and etf/lab.json (monthly IC and gates)
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, merit, sources
from .archive import Archive, write_json
from .lab import newey_west_t

RULES = json.loads((config.RULES_DIR / "etf.json").read_text(encoding="utf-8"))
SIGNALS = json.loads((config.RULES_DIR / "etf_signals.json").read_text(encoding="utf-8"))
UNIVERSE = RULES["universe"]
TICKERS = [u["ticker"] for u in UNIVERSE]
ROLE = {u["role"]: u["ticker"] for u in UNIVERSE}
IDX = {t: i for i, t in enumerate(TICKERS)}
CLASS = {u["ticker"]: u["class"] for u in UNIVERSE}
K = len(TICKERS)
CASH = ROLE["CASH"]
RISK = [t for t in TICKERS if t != CASH]
SECTORS = [u["ticker"] for u in UNIVERSE if u["class"] == "sector"]
EQUITY = [u["ticker"] for u in UNIVERSE if u["class"] in ("world", "region", "country", "factor")]
CAPITAL = float(RULES["capital_eur"])
COMMISSION = RULES["costs"]["commission"]
HALF = np.array([RULES["costs"]["spread_half"][CLASS[t]] for t in TICKERS])
TAX = RULES["tax"]["capital_gains"]
BAND = RULES["band"]
DAY = 21   # trading days per month
YEAR = 252
STRATEGIES = [s["id"] for s in RULES["strategies"]]
REFS = [r["id"] for r in RULES["references"]]
NAMES = {s["id"]: s["name"] for s in RULES["strategies"] + RULES["references"]}


def _a(root):
    return Archive(Path(root) / "etf") if not isinstance(root, Archive) else Archive(root.root / "etf")


# --- data ------------------------------------------------------------------------------------------------
def fetch(archive, now=None, history_from="2017-06-01"):
    """Appends new ETF prices (Yahoo, euro listings) to etf/raw/prices.csv. Returns the new row count."""
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    end = sources.last_closed_day(now_utc)
    a = _a(archive)
    p = a.read("prices")
    start = (pd.Timestamp(p["date"].max()) - pd.Timedelta(days=10)).date().isoformat() if len(p) else history_from
    from .sources import yahoo
    prices, _ = yahoo.fetch(TICKERS, start, end, raw_symbols=True)
    return a.append("prices", prices, now_utc.strftime("%Y-%m-%dT%H:%M:%S"))


def matrices(a):
    """Dates and days x ETF matrices of open and close (gaps filled from the previous close)."""
    p = a.read("prices")
    p = p[p["ticker"].isin(TICKERS)]
    close = p.pivot(index="date", columns="ticker", values="close").reindex(columns=TICKERS).astype(float)
    open_ = p.pivot(index="date", columns="ticker", values="open").reindex(columns=TICKERS).astype(float)
    cal = close[ROLE["WORLD"]].dropna().index   # the World ETF sets the calendar
    close = close.reindex(cal)
    open_ = open_.reindex(cal)
    valid = close.notna().to_numpy()
    close = close.ffill()
    open_ = open_.fillna(close.shift(1)).fillna(close)
    # an ETF that does not exist yet has price 0 here and is never held or ranked (valid is False)
    return list(cal), np.nan_to_num(close.to_numpy()), np.nan_to_num(open_.to_numpy()), valid


def month_ends(dates):
    """Index of each month's last trading day."""
    out = []
    for i, d in enumerate(dates):
        if i + 1 < len(dates):
            last = dates[i + 1][:7] != d[:7]
        else:   # the newest day counts only if the next business day is already in another month
            last = (pd.Timestamp(d) + pd.offsets.BDay(1)).strftime("%Y-%m") != d[:7]
        if last:
            out.append(i)
    return out


# --- signals ---------------------------------------------------------------------------------------------
@np.errstate(all="ignore")
def features(close, valid, i):
    """Signals at the close of day i from closes up to i only. NaN where the ETF lacks history."""
    f = {}
    n = lambda lag: close[i - lag] if i - lag >= 0 else np.full(K, np.nan)
    hist = valid[max(0, i - 253)] if i >= 253 else np.zeros(K, dtype=bool)
    ok = lambda x: np.where(hist, x, np.nan)
    f["mom_12m"] = ok(close[i] / n(YEAR) - 1)
    f["mom_12_1"] = ok(n(DAY) / n(YEAR) - 1)
    f["mom_6m"] = ok(close[i] / n(6 * DAY) - 1)
    f["mom_1m"] = ok(close[i] / n(DAY) - 1)
    if i >= 253:
        sma = close[i - 209:i + 1].mean(axis=0)   # about 10 months
        f["trend_10m"] = ok(close[i] / sma - 1)
        r = close[i - YEAR + 1:i + 1] / close[i - YEAR:i] - 1
        f["vol_12m"] = ok(r.std(axis=0, ddof=1) * np.sqrt(YEAR))
    else:
        f["trend_10m"] = f["vol_12m"] = np.full(K, np.nan)
    return f


def _w(**kw):
    w = np.zeros(K)
    for role, x in kw.items():
        w[IDX[ROLE[role]]] += x
    return w


def _eq(tickers):
    w = np.zeros(K)
    for t in tickers:
        w[IDX[t]] += 1 / len(tickers)
    return w


def _cash_fill(w):
    w = w.copy()
    w[IDX[CASH]] += max(0.0, 1.0 - w.sum())
    return w


def _above(f, t):
    return f["trend_10m"][IDX[t]] > 0


def _top(f, key, tickers, k, high=True):
    vals = [(f[key][IDX[t]], t) for t in tickers if not np.isnan(f[key][IDX[t]])]
    vals.sort(key=lambda x: (-x[0] if high else x[0], x[1]))
    return [t for _, t in vals[:k]]


def target(sid, f):
    """Target weights (sum 1, long only) of a strategy or reference from the features of the decision day."""
    R = ROLE
    if sid == "ref.world_hold":
        return _w(WORLD=1.0)
    if sid == "ref.60_40":
        return _w(WORLD=0.6, BOND_EZ=0.4)
    if sid == "s01.equal_core":
        return _eq([R[x] for x in ("WORLD", "EZ", "EM", "BOND_EZ", "BOND_INFL", "GOLD", "CASH")])
    if sid == "s02.risk_parity":
        ts = [R[x] for x in ("WORLD", "BOND_EZ", "BOND_GLOBAL", "BOND_INFL", "GOLD")]
        inv = {t: 1 / f["vol_12m"][IDX[t]] for t in ts if not np.isnan(f["vol_12m"][IDX[t]])}
        if not inv:
            return _w(CASH=1.0)
        s = sum(inv.values())
        w = np.zeros(K)
        for t, x in inv.items():
            w[IDX[t]] = x / s
        return w
    if sid == "s03.dual_momentum":
        pool = [R[x] for x in ("US", "EZ", "EM", "JP")]
        best = _top(f, "mom_12m", pool, 1)
        if not best or f["mom_12m"][IDX[best[0]]] <= f["mom_12m"][IDX[CASH]]:
            return _w(BOND_GLOBAL=1.0)
        return _eq(best)
    if sid == "s04.trend_gtaa":
        w = np.zeros(K)
        for t in [R[x] for x in ("US", "EM", "BOND_EZ", "GOLD", "WORLD")]:
            w[IDX[t if _above(f, t) else CASH]] += 0.2
        return w
    if sid == "s05.trend_world":
        return _w(WORLD=1.0) if _above(f, R["WORLD"]) else _w(CASH=1.0)
    if sid == "s06.sector_momentum":
        if not _above(f, R["WORLD"]):
            return _w(CASH=1.0)
        top = _top(f, "mom_6m", SECTORS, 3)
        return _cash_fill(_eq(top) if top else np.zeros(K))
    if sid == "s07.low_vol":
        low = _top(f, "vol_12m", EQUITY, 5, high=False)
        return _eq(low) if low else _w(CASH=1.0)
    if sid == "s08.factor_mix":
        return _eq([R[x] for x in ("QUAL", "VALUE", "SMALL")])
    if sid == "s09.all_weather":
        return _w(WORLD=0.3, BOND_MID=0.4, GOLD=0.15, CASH=0.15)
    if sid == "s10.asset_momentum":
        w = np.zeros(K)
        for t in _top(f, "mom_12_1", RISK, 5):
            w[IDX[t if f["mom_12m"][IDX[t]] > 0 else CASH]] += 0.2
        return _cash_fill(w)
    raise KeyError(sid)


# --- the portfolio simulator (one engine for strategies, references and monkeys) -------------------------
def run_portfolio(op, cl, decisions, start, end):
    """decisions: {decision_day_index: target weights}. Orders fill at the open of the next day.
    Returns (values[start..end], summary). Value is in EUR at the close, before tax."""
    shares = np.zeros(K)
    avg = np.zeros(K)            # cost in EUR of what is held
    cash = CAPITAL
    gains = {}
    costs = bought = sold = 0.0
    fills = sorted((d + 1, w) for d, w in decisions.items() if start <= d + 1 <= end)
    vals = np.full(end - start + 1, np.nan)
    prev = start
    for f_day, w in fills:
        vals[prev - start:f_day - start] = cash + cl[prev:f_day] @ shares
        prev = f_day
        o = op[f_day]
        v_open = cash + shares @ o
        cur = shares * o / v_open
        sell_sh = np.zeros(K)
        for k in range(K):
            if w[k] == 0 and shares[k] > 0:
                sell_sh[k] = shares[k]
            elif cur[k] - w[k] > BAND:
                sell_sh[k] = min(shares[k], (cur[k] - w[k]) * v_open / o[k])
        year = _year(f_day)
        for k in np.nonzero(sell_sh)[0]:
            n = sell_sh[k]
            gross = n * o[k]
            fee = gross * (HALF[k] + COMMISSION)
            cash += gross - fee
            costs += fee
            sold += gross
            part = n / shares[k]
            gains[year] = gains.get(year, 0.0) + (gross - fee) - avg[k] * part
            avg[k] *= 1 - part
            shares[k] -= n
        want = np.zeros(K)
        for k in range(K):
            if w[k] - shares[k] * o[k] / v_open > BAND or (w[k] > 0 and shares[k] == 0):
                want[k] = max(0.0, w[k] * v_open - shares[k] * o[k])
        total = want.sum()
        scale = min(1.0, cash / (total * 1.0 + 1e-12)) if total > 0 else 0.0
        for k in np.nonzero(want)[0]:
            eur = want[k] * scale
            fee = eur * (HALF[k] + COMMISSION) / (1 + HALF[k] + COMMISSION)
            net = eur - fee
            shares[k] += net / o[k]
            avg[k] += net + fee
            cash -= eur
            costs += fee
            bought += eur
    vals[prev - start:] = cash + cl[prev:end + 1] @ shares
    tax = TAX * sum(max(0.0, g) for g in gains.values())
    return vals, {"costs": round(costs, 2), "bought": round(bought, 2), "sold": round(sold, 2),
                  "realised_gains": {y: round(g, 2) for y, g in sorted(gains.items())}, "tax": round(tax, 2),
                  "cash": round(cash, 2), "holdings": {TICKERS[k]: round(float(shares[k] * cl[end][k] / vals[-1]), 4)
                                                       for k in range(K) if shares[k] > 1e-9}}


_YEAR_CACHE = {}
_DATES = []


def _year(i):
    return _DATES[i][:4]


# --- one league run over a window ----------------------------------------------------------------------
def decision_days(dates, start, end, ends):
    days = [start] + [i for i in ends if start < i < end]
    return days


def strategy_targets(close, valid, days):
    """{id: {decision_day: weights}} for the 10 strategies and the 2 references."""
    out = {s: {} for s in STRATEGIES + REFS}
    for d in days:
        f = features(close, valid, d)
        for s in STRATEGIES + REFS:
            if s == "ref.world_hold" and d != days[0]:
                continue
            out[s][d] = target(s, f)
    return out


def _rng(i, tag):
    return np.random.default_rng(int(hashlib.sha256(f"etf-monkey-{i:04d}|{tag}".encode()).hexdigest()[:16], 16))


def monkey_targets(strategy_t, i, days, eligible_at):
    """Monkey i copies strategy i mod 10: whenever that strategy changes its target (rotation), the monkey
    redraws random assets and gives them the same multiset of weights."""
    s = STRATEGIES[i % len(STRATEGIES)]
    rng = _rng(i, s)
    out, prev = {}, None
    for d in days:
        w = strategy_t[s][d]
        if prev is None or np.abs(w - prev).max() > 1e-9:
            weights = np.sort(w[w > 0])[::-1]
            pool = [k for k in range(K) if eligible_at[d][k]]
            pick = rng.choice(pool, size=min(len(weights), len(pool)), replace=False)
            m = np.zeros(K)
            m[pick] = weights[:len(pick)]
            out[d] = m / m.sum() if m.sum() else m
        prev = w
    return out


def simulate_window(dates, op, cl, valid, ends, start, end, n_monkeys):
    days = decision_days(dates, start, end, ends)
    st = strategy_targets(cl, valid, days)
    hist_ok = {d: valid[max(0, d - 253)] if d >= 253 else np.zeros(K, bool) for d in days}
    eligible = {d: hist_ok[d] | (np.arange(K) == IDX[CASH]) for d in days}
    values, info = {}, {}
    for s in REFS + STRATEGIES:
        values[s], info[s] = run_portfolio(op, cl, st[s], start, end)
    monkeys = np.zeros((n_monkeys, end - start + 1))
    for i in range(n_monkeys):
        monkeys[i], _ = run_portfolio(op, cl, monkey_targets(st, i, days, eligible), start, end)
    return values, info, monkeys, st


# --- shadow signals and Signal Lab (monthly) ---------------------------------------------------------------
def lab(a, dates, cl, valid, ends, day_zero):
    """Writes every pre-registered signal (append-only) and its monthly rank IC against next month's return."""
    gates = SIGNALS["gates"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    key = {"etf.mom_12_1": "mom_12_1", "etf.mom_6m": "mom_6m", "etf.trend_10m": "trend_10m",
           "etf.low_vol_12m": "vol_12m", "etf.short_reversal": "mom_1m"}
    flip = {"etf.low_vol_12m": -1.0}
    rows, series = [], {s["id"]: [] for s in SIGNALS["signals"]}
    reh = {s["id"]: [] for s in SIGNALS["signals"]}
    for n, i in enumerate(ends):
        if i < 253:
            continue
        f = features(cl, valid, i)
        nxt = ends[n + 1] if n + 1 < len(ends) else None
        fwd = (cl[nxt] / cl[i] - 1) if nxt else None
        ok = np.array([t != CASH and valid[i - 253][IDX[t]] for t in TICKERS])
        for s in SIGNALS["signals"]:
            v = f[key[s["id"]]] * flip.get(s["id"], 1.0)
            if dates[i] < day_zero:   # pre-registered on 2026-11-19: only later observations count
                if fwd is not None and ok.sum() >= 10:
                    ic = pd.Series(v[ok]).rank().corr(pd.Series(fwd[ok]).rank())
                    if not np.isnan(ic):
                        reh[s["id"]].append(float(ic) * s["expected_sign"])
                continue
            for k in np.nonzero(ok)[0]:
                rows.append({"date": dates[i], "ticker": TICKERS[k], "signal_id": s["id"], "value": round(float(v[k]), 6)})
            if fwd is not None and ok.sum() >= 10:
                ic = pd.Series(v[ok]).rank().corr(pd.Series(fwd[ok]).rank())   # Spearman without scipy
                if not np.isnan(ic):
                    series[s["id"]].append((dates[i], float(ic) * s["expected_sign"]))
    p = a.root / "signals.csv"
    old = pd.read_csv(p, dtype=str) if p.exists() else pd.DataFrame(columns=["date", "ticker", "signal_id", "value", "recorded_at"])
    seen = set(zip(old["date"], old["ticker"], old["signal_id"]))
    new = pd.DataFrame([{**r, "recorded_at": now} for r in rows if (r["date"], r["ticker"], r["signal_id"]) not in seen])
    if len(new):
        a.root.mkdir(parents=True, exist_ok=True)
        pd.concat([old, new]).to_csv(p, index=False, lineterminator="\n")
    out = {}
    for s in SIGNALS["signals"]:
        ics = [x for _, x in series[s["id"]]]
        sub = [float(np.mean(c)) for c in np.array_split(np.array(ics), gates["subperiods"]) if len(c)] if len(ics) >= gates["subperiods"] else []
        t = newey_west_t(ics, gates["nw_lag"]) if len(ics) >= 3 else None
        g = {"months": len(ics) >= gates["min_months"],
             "nw_t": t is not None and t > gates["min_nw_t"],
             "stable": sum(1 for x in sub if x > 0) >= gates["min_same_sign_subperiods"]}
        out[s["id"]] = {"family": s["family"], "rehearsal_months": len(reh[s["id"]]),
                        "rehearsal_mean_ic": None if not reh[s["id"]] else round(float(np.mean(reh[s["id"]])), 4),
                        "months": len(ics), "mean_ic": None if not ics else round(float(np.mean(ics)), 4),
                        "nw_t": None if t is None else round(t, 2), "gates": g,
                        "status": "passes_gates" if all(g.values()) else "collecting"}
    return out


# --- statistics -------------------------------------------------------------------------------------------
def _stats(values, base, op_info, world, monkeys, trials, dates):
    v = np.asarray(values)
    r = v[1:] / v[:-1] - 1
    ret = v[-1] / v[0] - 1
    peak = np.maximum.accumulate(v)
    out = {"value": round(float(v[-1]), 2), "return": round(float(ret), 4),
           "volatility": round(float(r.std(ddof=1) * np.sqrt(YEAR)), 4) if len(r) > 2 else None,
           "max_drawdown": round(float((1 - v / peak).max()), 4), "costs": op_info["costs"],
           "turnover_per_year": round(op_info["sold"] / max(v.mean(), 1) * YEAR / max(len(r), 1), 3),
           "tax": op_info["tax"], "value_after_tax": round(float(v[-1]) - op_info["tax"], 2),
           "return_after_tax": round((float(v[-1]) - op_info["tax"]) / v[0] - 1, 4),
           "vs_world_after_tax": None, "beats_monkeys": None, "holdings": op_info["holdings"]}
    w = world["value_after_tax"]
    out["vs_world_after_tax"] = round(out["value_after_tax"] / w - 1, 4) if w else None
    mret = monkeys[:, -1] / monkeys[:, 0] - 1
    out["beats_monkeys"] = round(float((mret < ret).mean()), 4)
    if len(r) >= 20:
        sr = merit.sharpe(r)
        sk, ku = merit.moments(r)
        n, rho, neff, srs = trials
        srs = [x for x in srs if x is not None]
        var = float(np.var(srs, ddof=1)) if len(srs) > 1 else 0.0
        out["sharpe_year"] = None if sr is None else round(sr * np.sqrt(YEAR), 3)
        d = merit.dsr(sr, len(r), sk, ku, neff, var) if sr is not None else None
        out["dsr"] = None if d is None else round(d, 4)
        mt = merit.min_trl(sr, sk, ku) if sr is not None else None
        out["min_track_record_years"] = None if mt is None else round(mt / YEAR, 1)
    return out


def block(dates, values, info, monkeys, start, end, label):
    ds = dates[start:end + 1]
    daily = {s: pd.Series(values[s]).pct_change().dropna().tolist() for s in STRATEGIES}
    srs = [merit.sharpe(daily[s]) for s in STRATEGIES]
    ser = {s: dict(zip(ds[1:], daily[s])) for s in STRATEGIES}
    n, rho, neff = merit.effective_trials(ser)
    trials = (n, rho, neff, srs)
    world = {"value_after_tax": round(float(values["ref.world_hold"][-1]) - info["ref.world_hold"]["tax"], 2)}
    parts = {s: _stats(values[s], CAPITAL, info[s], world, monkeys, trials, ds) for s in REFS + STRATEGIES}
    for s in parts:
        parts[s]["name"] = NAMES[s]
    mret = monkeys[:, -1] / monkeys[:, 0] - 1
    q = np.quantile(mret, [0.05, 0.5, 0.95])
    months = round((len(ds) - 1) / DAY, 1)
    best = max(STRATEGIES, key=lambda s: parts[s]["return_after_tax"])
    return {"label": label, "from": ds[0], "to": ds[-1], "days": len(ds) - 1, "months": months,
            "participants": parts, "monkeys": {"n": int(monkeys.shape[0]), "p05": round(float(q[0]), 4),
            "median": round(float(q[1]), 4), "p95": round(float(q[2]), 4), "best_of_n": round(float(mret.max()), 4)},
            "best_strategy": best, "trials": {"n": n, "mean_correlation": round(rho, 3), "n_eff": round(neff, 2)}}


def verdict(live):
    """The pre-set success and failure rules applied to the live window."""
    s = RULES["success"]
    m = live["months"]
    world = live["participants"]["ref.world_hold"]
    items = {}
    for sid in STRATEGIES:
        p = live["participants"][sid]
        dd_fail = p["max_drawdown"] > s["fail_drawdown"]
        if m < s["min_months"]:
            status = "too early" if not dd_fail else "failed (drawdown)"
        else:
            win = (p["beats_monkeys"] or 0) >= s["beat_monkeys_percentile"] and p["value_after_tax"] > world["value_after_tax"]
            lose = m >= s["fail_months"] and p["value_after_tax"] < world["value_after_tax"]
            status = "failed (drawdown)" if dd_fail else "success" if win else "failed (below the World ETF)" if lose else "open"
        items[sid] = status
    return {"months_live": m, "min_months": s["min_months"], "per_strategy": items}


def run(archive, fetch_data=True):
    """The nightly step of the league. Returns a small summary (counts and ok only)."""
    a = _a(archive)
    cfg_path = a.root / "league.json"
    if not cfg_path.exists():
        return {"status": "no league yet (run: python -m arena etf --create)"}
    league = json.loads(cfg_path.read_text(encoding="utf-8"))
    n_new = fetch(archive) if fetch_data else 0
    dates, cl, op, valid = matrices(a)
    global _DATES
    _DATES = dates
    ends = month_ends(dates)
    n_m = RULES["monkeys"]
    day0 = max(i for i, d in enumerate(dates) if d <= league["day_zero"])
    out = {"version": RULES["version"], "generated_for": dates[-1], "universe_frozen_on": RULES["universe_frozen_on"],
           "note": "Fictional money, simulation only. Values before tax unless stated. The live window is the only evidence; the rehearsal is a technical test on past data."}
    rs = next(i for i, d in enumerate(dates) if d >= RULES["rehearsal_start"])
    reh = simulate_window(dates, op, cl, valid, ends, rs, day0, min(n_m, 300))
    out["rehearsal"] = block(dates, reh[0], reh[1], reh[2], rs, day0, "technical rehearsal (past data, not evidence)")
    if len(dates) - 1 > day0:
        liv = simulate_window(dates, op, cl, valid, ends, day0, len(dates) - 1, n_m)
        out["live"] = block(dates, liv[0], liv[1], liv[2], day0, len(dates) - 1, "live league (from day zero)")
        out["verdict"] = verdict(out["live"])
        ds = dates[day0:]
        pd.DataFrame({s: liv[0][s] for s in REFS + STRATEGIES}, index=ds).round(2).to_csv(
            a.root / "values.csv", index_label="date", lineterminator="\n")
        mq = np.quantile(liv[2], [0.05, 0.5, 0.95], axis=0)
        pd.DataFrame({"p05": mq[0], "p50": mq[1], "p95": mq[2], "best": liv[2].max(axis=0)}, index=ds).round(2).to_csv(
            a.root / "monkeys.csv", index_label="date", lineterminator="\n")
    else:
        out["live"] = None
        out["verdict"] = {"months_live": 0, "note": "day zero; first fills at the next open"}
    out["signals"] = lab(a, dates, cl, valid, ends, league["day_zero"])
    write_json(a.root / "report.json", json.loads(json.dumps(out, allow_nan=False, default=float)))
    return {"status": "ok", "new_rows": n_new, "until": dates[-1], "live_days": max(0, len(dates) - 1 - day0)}


def create(archive, day_zero=None):
    a = _a(archive)
    p = a.root / "league.json"
    if p.exists():
        raise SystemExit("the ETF League already has a day zero")
    fetch(archive)
    dates, *_ = matrices(a)
    d0 = day_zero or dates[-1]
    write_json(p, {"name": "ETF League", "day_zero": d0, "created_on": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                   "rules_version": RULES["version"], "universe_frozen_on": RULES["universe_frozen_on"],
                   "capital_eur": CAPITAL, "note": "Fictional money. Live window starts at day zero; everything before is a technical rehearsal."})
    return d0
