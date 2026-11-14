"""Builds the website from the journal (design ch. 9).

The site is static: the built files in site/dist (index.html, app.js, arena3d.js, style.css, ...)
are copied next to a generated data.js (window.ARENA = {...}). data.js lives only in the private
archive. Opening site/index.html from disk also works (no server needed).
"""
import json
import re
import shutil

from . import config
from .metrics import INDEX, indicators, label

# Species in the order of rules/population.json -> stable keys used by the site (colours, 3D sectors).
SPECIES_KEYS = ["trend", "contrarian", "value", "news", "balanced"]
SPECIES_EN = {   # short labels for the one-look page (full descriptions live in rules/population.json)
    "trend": ("Trend", "Buys what is rising"),
    "contrarian": ("Contrarian", "Buys what fell too far"),
    "value": ("Value", "Good, cheap companies; trades little"),
    "news": ("News", "Reacts to the news"),
    "balanced": ("Balanced", "A bit of everything, low risk"),
}
TYPE = {"agent": "agent", "monkey": "monkey", "index": "index", "equal_weight": "equal"}
SIGNAL_LABEL = {
    "mom_1m": "Trend 1M", "mom_3m": "Trend 3M", "mom_6m": "Trend 6M", "mom_12m": "Trend 12M",
    "rev_1w": "Dip 1W", "rev_1m": "Dip 1M", "low_risk": "Low risk", "near_high": "Near high",
    "news": "News", "value": "Value", "quality": "Quality",
}
LOG_MAX = 20          # moves per participant kept in the site (the full journal stays in the archive)
DIST = config.SITE_TEMPLATE_DIR / "dist"


def build(archive):
    out = archive.root / "site"
    data = build_data(archive, archive.journal_days())   # first: a failure leaves the old site intact
    out.mkdir(parents=True, exist_ok=True)
    for f in out.iterdir():   # empty the folder (old files from earlier versions must not linger)
        shutil.rmtree(f) if f.is_dir() else f.unlink()
    shutil.copytree(DIST, out, dirs_exist_ok=True)
    text = "window.ARENA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (out / "data.js").write_text(text, encoding="utf-8", newline="\n")
    return data


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _r(x, c=6):
    return None if x is None else round(float(x), c)


def build_data(archive, days):
    cfg = archive.cfg
    species_names = list(config.POPULATION["species"].keys())
    sp_key = {e: SPECIES_KEYS[i] if i < len(SPECIES_KEYS) else f"s{i}" for i, e in enumerate(species_names)}
    meta = {"mode": "live" if cfg.get("mode") == "official" else "trial", "dayZero": cfg.get("day_zero"),
            "capital": config.CAPITAL, "rules": config.RULES_VERSION, "engine": config.ENGINE_VERSION}
    species = {sp_key[e]: {"label": SPECIES_EN.get(sp_key[e], (e, ""))[0], "about": SPECIES_EN.get(sp_key[e], ("", ""))[1]}
               for e in species_names}
    if not days:
        return {"meta": {**meta, "updated": None, "dates": []}, "species": species, "p": [], "band": [], "day": None}

    series, logs = {}, {}
    last = prev = None
    for d in days:
        j = archive.read_journal(d)
        prev, last = last, j
        for name, dec in j["decisions"].items():
            lg = logs.setdefault(name, [])
            for f in dec["fills"]:
                lg.append({"d": d, "k": f["side"], "t": f["ticker"], "eur": f["eur"], "px": f["price_usd"], "n": f["shares"],
                           "fee": round(f["fx_cost_eur"] + f["slippage_cost_eur"], 2),
                           "gain": f.get("gain_eur"), "why": (f.get("reason") or {}).get("text", "")})
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
            dna = {"w": {SIGNAL_LABEL.get(k, k): v for k, v in dna_in.get("weights", {}).items()},
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
            "next": [{"k": o["side"], "t": o["ticker"], "eur": o.get("eur"), "all": o.get("all"),
                      "why": (o.get("reason") or {}).get("text", "")} for o in p["pending"]],
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
    return {"meta": {**meta, "updated": today, "dates": days}, "species": species, "p": out, "band": band, "day": day}


def _prices(archive, last):
    """Last close of every holding, in EUR per share."""
    from .view import View
    view = View(archive, last["date"], last["inputs"]["cutoff"])
    rate = last["market"]["eurusd"]
    tickers = {t for p in last["state"]["participants"].values() for t in p["positions"]}
    return {t: (view.close(t, last["date"]) or view.last_close(t) or 0) / rate for t in tickers}
