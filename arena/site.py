"""Builds the website from the journal (design ch. 9, Experience v2).

The site is static: the built app in site/dist is copied next to generated data, which lives only in
the private archive (and online only behind the login):
  data/arena.json            everything the one-look page and the cards need, as of the last night
  data/days/YYYY-MM-DD.json  one shard per night for the Time Machine: values, holdings, trades,
                             market and the journal's fingerprints (provenance)
"""
import hashlib
import json
import re
import shutil

from . import config
from .metrics import INDEX, indicators, label

# Species keys = their prefix in lower case (arrow, wave, rock, echo, plumb, later mirror, compass): stable
# across renames of the long names and used by the site for colours and 3D sectors.
SPECIES_ABOUT = {   # short one-liners for the page (full descriptions live in rules/population.json)
    "arrow": "Buys what is rising", "wave": "Buys what fell too far", "rock": "Good, cheap companies; trades little",
    "echo": "Reacts to the news", "plumb": "A bit of everything, low risk",
    "mirror": "Copies insiders and politicians", "compass": "Follows the macro picture",
}
TYPE = {"agent": "agent", "monkey": "monkey", "index": "index", "equal_weight": "equal"}
SIGNAL_LABEL = {
    "mom_1m": "Trend 1M", "mom_3m": "Trend 3M", "mom_6m": "Trend 6M", "mom_12m": "Trend 12M",
    "rev_1w": "Dip 1W", "rev_1m": "Dip 1M", "low_risk": "Low risk", "near_high": "Near high",
    "news": "News", "value": "Value", "quality": "Quality",
}
LOG_MAX = 20          # moves per participant kept in the site (the full journal stays in the archive)
DIST = config.SITE_TEMPLATE_DIR / "dist"


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def build(archive):
    out = archive.root / "site"
    days = archive.journal_days()
    data = build_data(archive, days)   # first: a failure leaves the old site intact
    shards = {d: _shard(archive.read_journal(d), archive.journal_path(d)) for d in days}
    out.mkdir(parents=True, exist_ok=True)
    for f in out.iterdir():   # empty the folder (old files from earlier versions must not linger)
        shutil.rmtree(f) if f.is_dir() else f.unlink()
    shutil.copytree(DIST, out, dirs_exist_ok=True)
    (out / "data" / "days").mkdir(parents=True, exist_ok=True)
    (out / "data" / "arena.json").write_text(_dump(data), encoding="utf-8", newline="\n")
    for d, sh in shards.items():
        (out / "data" / "days" / f"{d}.json").write_text(_dump(sh), encoding="utf-8", newline="\n")
    return data


def readings_text(cols, z):
    """Canonical text of a night's signal readings (z-scores, 6 decimals). The browser rebuilds the same text
    from the shard and checks its SHA-256 (the Verify button), then recomputes every decision from it."""
    return "".join(f"{t}|" + ",".join(f"{v:.6f}" for v in z[t]) + "\n" for t in sorted(z)) + "cols|" + ",".join(cols) + "\n"


def _readings(j):
    cols = list(config.PRICE_SIGNALS)
    sig = j.get("signals") or {}
    z = {t: [round(float(r["z"].get(c, 0.0) or 0.0), 6) for c in cols] for t, r in sig.items()}
    raw = {t: [None if r.get("raw", {}).get(c) is None else round(float(r["raw"][c]), 6) for c in cols] for t, r in sig.items()}
    return cols, z, raw


def _shard(j, path=None):
    """One night, as it was known then: what the Time Machine replays, plus the readings behind every
    decision taken that night (for the Why? waterfall and Verify)."""
    st = j["state"]["participants"]
    cols, z, raw = _readings(j)
    text = readings_text(cols, z)
    return {
        "date": j["date"], "version": j.get("version"), "inputs": j.get("inputs"),
        "journalSha256": hashlib.sha256(path.read_bytes()).hexdigest() if path is not None and path.exists() else None,
        "sig": {"cols": cols, "z": z, "raw": raw, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()},
        "delisted": sorted((j["state"].get("delisted") or {}).keys()),
        "market": j.get("market"), "excluded": (j.get("checks") or {}).get("excluded", []),
        "values": {_slug(n): round(v, 2) for n, v in j["values"].items()},
        "cash": {_slug(n): round(p["cash"], 2) for n, p in st.items()},
        "positions": {_slug(n): {t: round(pos["shares"], 6) for t, pos in p["positions"].items()} for n, p in st.items()},
        "fills": [{"id": _slug(n), "k": f["side"], "t": f["ticker"], "eur": f["eur"]}
                  for n, dec in j["decisions"].items() for f in dec["fills"]],
        "pending": {_slug(n): len(p["pending"]) for n, p in st.items() if p["pending"]},
        "rule_changes": j.get("rule_changes"),
    }


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _r(x, c=6):
    return None if x is None else round(float(x), c)


def build_data(archive, days):
    cfg = archive.cfg
    sp_all = config.POPULATION["species"]
    sp_key = {e: (v.get("prefix") or e).lower() for e, v in sp_all.items()}
    meta = {"mode": "live" if cfg.get("mode") == "official" else "trial", "dayZero": cfg.get("day_zero"),
            "capital": config.CAPITAL, "rules": config.RULES_VERSION, "engine": config.ENGINE_VERSION}
    species = {sp_key[e]: {"label": v.get("prefix") or e, "family": e, "about": SPECIES_ABOUT.get(sp_key[e], v.get("description", ""))}
               for e, v in sp_all.items()}
    meta["signals"] = {k: SIGNAL_LABEL.get(k, k) for k in config.SIGNALS}
    meta["evidence"] = _evidence(archive)
    if not days:
        return {"meta": {**meta, "updated": None, "dates": [], "marks": []}, "species": species, "p": [], "band": [], "day": None}

    series, logs, fills_by_day, rule_days = {}, {}, {}, []
    last = prev = None
    for d in days:
        j = archive.read_journal(d)
        prev, last = last, j
        dd = prev["date"] if prev else None    # the night the order was decided (filled at today's open)
        if j.get("rule_changes"):
            rule_days.append(d)
        for name, dec in j["decisions"].items():
            lg = logs.setdefault(name, [])
            if dec["fills"]:
                fills_by_day.setdefault(d, []).append(_slug(name))
            for f in dec["fills"]:
                lg.append({"d": d, "dd": dd, "k": f["side"], "t": f["ticker"], "eur": f["eur"], "px": f["price_usd"], "n": f["shares"],
                           "fee": round(f["fx_cost_eur"] + f["slippage_cost_eur"], 2),
                           "gain": f.get("gain_eur"), "why": (f.get("reason") or {}).get("text", ""), "r": _reason(f.get("reason"))})
            for ev in dec["events"]:
                lg.append({"d": d, "k": ev["type"], "t": ev["ticker"], "eur": ev.get("eur"), "ratio": ev.get("ratio")})
            for c in dec["cancelled"]:
                lg.append({"d": d, "k": "cancelled", "t": c["ticker"], "why": f"Cancelled: {c['cause']}."})
        for name, v in j["values"].items():
            series.setdefault(name, []).append((d, v))

    state = last["state"]
    today = last["date"]
    index_series = series[INDEX]
    monkeys = {n: series[n] for n, p in state["participants"].items() if p["type"] == "monkey"}
    inds = {n: indicators(n, series[n], index_series, p, monkeys, today[:4]) for n, p in state["participants"].items()}
    monkey_scores = [inds[n]["score"] for n in monkeys]
    prices = _prices(archive, last)

    out = []
    for name, p in state["participants"].items():
        ind = inds[name]
        kind = TYPE.get(p["type"], p["type"])
        total = ind["value"] or 1
        hold = []
        for t, pos in p["positions"].items():
            eur = round(pos["shares"] * prices.get(t, 0), 2)
            hold.append({"t": t, "name": config.NAMES.get(t, "S&P 500 TR" if t == config.INDEX_TOTAL else t),
                         "n": pos["shares"], "eur": eur, "w": round(eur / total, 4),
                         "gain": round(eur / pos["cost_eur"] - 1, 4) if pos["cost_eur"] else None, "since": pos["since"]})
        hold.sort(key=lambda h: -h["eur"])
        dna_in = p.get("dna") or {}
        dna = None
        if kind == "agent" and dna_in:
            dna = {"w": dict(dna_in.get("weights", {})), "minHold": dna_in.get("min_hold_days"), "band": dna_in.get("rank_band"),
                   "picks": dna_in.get("n_holdings"), "maxW": dna_in.get("max_weight"), "review": dna_in.get("review_days"),
                   "stop": dna_in.get("stop_loss"), "brake": dna_in.get("brake")}
        badge = label(ind, monkey_scores) if kind == "agent" else None
        out.append({
            "id": _slug(name), "name": name, "type": kind, "sp": sp_key.get(p["species"]),
            "born": p["born"], "parents": p.get("parents"), "copies": p.get("copies_management_of"),
            "value": ind["value"], "ret": ind["return"], "vsIdx": ind["vs_index"],
            "score": ind["score"], "beatsMonkeys": ind["beats_monkeys"],
            "merit": badge == "merit" if badge else None,
            "vol": ind["volatility"], "mdd": ind["max_drawdown"], "fees": ind["costs"], "divs": ind["dividends"],
            "turnover": ind["turnover"], "hit": ind["hit_rate"], "closed": ind["closed_trades"],
            "tax": ind["estimated_tax"], "cash": round(p["cash"], 2), "days": ind["days"],
            "s": [round(v, 2) for _, v in series[name]], "from": series[name][0][0],
            "dna": dna, "hold": hold,
            "next": [{"k": o["side"], "t": o["ticker"], "eur": o.get("eur"), "all": o.get("all"), "dd": today,
                      "why": (o.get("reason") or {}).get("text", ""), "r": _reason(o.get("reason"))} for o in p["pending"]],
            "log": list(reversed(logs.get(name, [])))[:LOG_MAX],
        })

    band = []
    for i in range(len(days)):
        vals = [s[i][1] for s in monkeys.values() if i < len(s)]
        band.append([round(min(vals), 2), round(max(vals), 2)] if vals else None)

    m, m0 = last["market"], (prev or {}).get("market") or {}
    fills = [f for dec in last["decisions"].values() for f in dec["fills"]]
    day = {"date": today, "buys": sum(f["side"] == "buy" for f in fills), "sells": sum(f["side"] == "sell" for f in fills),
           "spx": _r(m["sp500"] / m0["sp500"] - 1) if m.get("sp500") and m0.get("sp500") else None,
           "eurusd": m.get("eurusd"), "aboveMa200": m.get("above_ma"),
           "orders": sum(len(p["pending"]) for p in state["participants"].values()),
           "excluded": len(last["checks"]["excluded"])}
    luck = _luck(archive, days, out)
    marks = [{"d": d, "k": "rules", "label": "Rule change"} for d in rule_days]
    idx_s = [v for _, v in index_series]
    moves = sorted(((idx_s[i] / idx_s[i - 1] - 1, days[i]) for i in range(1, len(idx_s)) if idx_s[i - 1]), key=lambda x: -abs(x[0]))[:3]
    marks += [{"d": d, "k": "market", "label": f"S&P 500 {'+' if m > 0 else ''}{m * 100:.1f}%"} for m, d in moves if abs(m) >= 0.015]
    first = min(fills_by_day) if fills_by_day else None
    if first:
        marks.append({"d": first, "k": "start", "label": "First trades"})
    return {"meta": {**meta, "updated": today, "dates": days, "marks": sorted(marks, key=lambda m: m["d"])},
            "species": species, "p": out, "band": band, "luck": luck, "day": day, "fillsByDay": fills_by_day}


def _reason(r):
    """Structured reason of an order: cause, score, rank and the main drivers (for the Why? waterfall)."""
    if not r:
        return None
    out = {k: r.get(k) for k in ("cause", "score", "rank", "of", "seed") if r.get(k) is not None}
    if r.get("drivers"):
        out["drivers"] = [{"s": d["signal"], "z": d.get("z"), "w": d.get("weight"), "term": d.get("term"), "raw": d.get("raw")}
                          for d in r["drivers"]]
    return out


def _evidence(archive):
    """Evidence status of each signal from the Signal Lab (lab/report.json), if present."""
    f = archive.root / "lab" / "report.json"
    try:
        sig = json.loads(f.read_text(encoding="utf-8")).get("signals", {}) if f.exists() else {}
    except (ValueError, OSError):
        return {}
    out = {}
    for k, v in sig.items():
        name = k.split(".", 1)[-1]
        out[name] = {"status": v.get("status"), "obs": v.get("observations"), "ic": v.get("mean_ic"), "t": v.get("nw_t")}
    return out


def _luck(archive, days, out):
    """Luck band from the 1,000 offline monkeys (monkeys/summary.json), if the night produced it.
    Adds to each agent its percentile against all monkeys and against the monkeys that mirror it."""
    f = archive.root / "monkeys" / "summary.json"
    if not f.exists():
        return None
    try:
        s = json.loads(f.read_text(encoding="utf-8"))
        b = s["luck_band"]
        by_date = dict(zip(b["dates"], zip(b["p05"], b["p95"])))
        series = [[round(by_date[d][0], 6), round(by_date[d][1], 6)] if d in by_date else None for d in days]
        for p in out:
            a = s.get("agents", {}).get(p["name"])
            if a:
                p["pctAll"] = a.get("percentile_vs_all_monkeys")
                p["pctMirror"] = a.get("percentile_vs_mirroring_monkeys")
        return {"n": s.get("monkeys"), "date": s.get("date"), "p05": _r(s.get("return_p05")), "median": _r(s.get("return_median")),
                "p95": _r(s.get("return_p95")), "best": _r(s.get("best_of_n")), "s": series}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):   # a malformed file never breaks the site
        return None


def _prices(archive, last):
    """Last close of every holding, in EUR per share."""
    from .view import View
    view = View(archive, last["date"], last["inputs"]["cutoff"])
    rate = last["market"]["eurusd"]
    tickers = {t for p in last["state"]["participants"].values() for t in p["positions"]}
    return {t: (view.close(t, last["date"]) or view.last_close(t) or 0) / rate for t in tickers}
