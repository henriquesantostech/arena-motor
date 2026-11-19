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
    (out / "data" / "journal").mkdir(parents=True, exist_ok=True)
    (out / "data" / "arena.json").write_text(_dump(data), encoding="utf-8", newline="\n")
    for d, sh in shards.items():
        (out / "data" / "days" / f"{d}.json").write_text(_dump(sh), encoding="utf-8", newline="\n")
    pages = journal_pages(archive, days, data)
    for d, page in pages.items():
        (out / "data" / "journal" / f"{d}.json").write_text(_dump(page), encoding="utf-8", newline="\n")
    (out / "data" / "corpus.json").write_text(_dump(corpus(data, pages)), encoding="utf-8", newline="\n")
    copy_intel(archive, out / "data")
    return data


# Phase 2 intelligence exports (written by the "intel" workflow) and the Signal Lab reports, copied as they
# are for the X5 lenses. Personal-use and non-commercial sources: only ever served behind the login.
INTEL_FILES = {
    "intel/site/world.json": "intel/world.json", "intel/site/graph.json": "intel/graph.json",
    "intel/site/alerts.json": "intel/alerts.json", "intel/site/docs.json": "intel/docs.json",
    "intel/lab/ic_provisional.json": "lab/ic_provisional.json", "intel/lab/mirror_book.json": "lab/mirror_book.json",
    "lab/report.json": "lab/report.json",
    "evolution/tree.json": "evolution/tree.json", "evolution/null.json": "evolution/null.json",
    "merit/report.json": "merit/report.json",
}


def copy_intel(archive, data_dir):
    present = {}
    for src, dst in INTEL_FILES.items():
        f = archive.root / src
        if f.exists() and _read_json(f) is not None:   # only well-formed files
            (data_dir / dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, data_dir / dst)
            present[dst] = True
    (data_dir / "intel").mkdir(parents=True, exist_ok=True)
    (data_dir / "intel" / "index.json").write_text(_dump(present), encoding="utf-8", newline="\n")


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
    meta["generation"] = config.POPULATION.get("generation", 1)
    meta["companies"] = {c["ticker"]: {"name": c["name"], "sector": c.get("sector")} for c in config.UNIVERSE["companies"]}   # names, not tickers, for lay readers
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
    merit = _read_json(archive.root / "merit" / "report.json") or {}
    merit_rows = merit.get("agents", {}) if isinstance(merit.get("agents"), dict) else {}
    meta["meritEvidence"] = merit.get("evidence")
    meta["generation"] = max([p.get("generation", 1) for p in state["participants"].values() if p["type"] == "agent"] or [1])

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
        row = merit_rows.get(name) if kind == "agent" else None
        badge = label(ind, monkey_scores, row) if kind == "agent" else None   # merit badge v2 (rules 1.2)
        out.append({
            "id": _slug(name), "name": name, "type": kind, "sp": sp_key.get(p["species"]),
            "born": p["born"], "parents": p.get("parents"), "copies": p.get("copies_management_of"),
            "value": ind["value"], "ret": ind["return"], "vsIdx": ind["vs_index"],
            "score": ind["score"], "beatsMonkeys": ind["beats_monkeys"],
            "merit": badge == "merit" if badge else None,
            "badge": (row or {}).get("badge") or badge, "badgeMissing": (row or {}).get("badge_missing"),
            "generation": p.get("generation", 1) if kind == "agent" else None, "immigrant": p.get("immigrant", False) if kind == "agent" else None,
            "vol": ind["volatility"], "mdd": ind["max_drawdown"], "fees": ind["costs"], "divs": ind["dividends"],
            "turnover": ind["turnover"], "hit": ind["hit_rate"], "closed": ind["closed_trades"],
            "tax": ind["estimated_tax"], "cash": round(p["cash"], 2), "days": ind["days"],
            "s": [round(v, 2) for _, v in series[name]], "from": series[name][0][0],
            "dna": dna, "hold": hold,
            "next": [{"k": o["side"], "t": o["ticker"], "eur": o.get("eur"), "all": o.get("all"), "dd": today,
                      "why": (o.get("reason") or {}).get("text", ""), "r": _reason(o.get("reason"))} for o in p["pending"]],
            "log": list(reversed(logs.get(name, [])))[:LOG_MAX],
        })

    # The graveyard (rules 1.2): dead agents keep a read-only card forever, with their history up to death.
    dead = []
    for name, rec in (state.get("graveyard") or {}).items():
        if name not in series or len(series[name]) < 1:
            continue
        death = rec.get("death") or {}
        try:
            ind = indicators(name, series[name], index_series, rec, monkeys, today[:4])
        except (KeyError, ValueError, ZeroDivisionError):
            continue
        dna_in = rec.get("dna") or {}
        total = sum(pos.get("cost_eur", 0) for pos in rec.get("positions", {}).values()) + rec.get("cash", 0) or 1
        dead.append({
            "id": _slug(name), "name": name, "type": "agent", "sp": sp_key.get(rec.get("species")), "dead": {
                "died": death.get("died"), "evaluation": death.get("evaluation"), "rank": death.get("rank"), "of": death.get("of"),
                "vs_index": death.get("vs_index"), "value": death.get("value"), "fitness": death.get("fitness")},
            "born": rec.get("born"), "parents": rec.get("parents"), "copies": None,
            "value": ind["value"], "ret": ind["return"], "vsIdx": ind["vs_index"], "score": None, "beatsMonkeys": None,
            "merit": False, "badge": "dead", "badgeMissing": None, "generation": rec.get("generation", 1), "immigrant": rec.get("immigrant", False),
            "vol": ind["volatility"], "mdd": ind["max_drawdown"], "fees": ind["costs"], "divs": ind["dividends"],
            "turnover": ind["turnover"], "hit": ind["hit_rate"], "closed": ind["closed_trades"], "tax": ind["estimated_tax"],
            "cash": round(rec.get("cash", 0), 2), "days": ind["days"],
            "s": [round(v, 2) for _, v in series[name]], "from": series[name][0][0],
            "dna": {"w": dict(dna_in.get("weights", {})), "minHold": dna_in.get("min_hold_days"), "band": dna_in.get("rank_band"),
                    "picks": dna_in.get("n_holdings"), "maxW": dna_in.get("max_weight"), "review": dna_in.get("review_days"),
                    "stop": dna_in.get("stop_loss"), "brake": dna_in.get("brake")} if dna_in else None,
            # frozen book at death, weighted by cost (prices of that night are not kept here)
            "hold": sorted(({"t": t, "name": config.NAMES.get(t, t), "n": pos["shares"], "eur": round(pos.get("cost_eur", 0), 2),
                             "w": round(pos.get("cost_eur", 0) / total, 4), "gain": None, "since": pos.get("since")}
                            for t, pos in rec.get("positions", {}).items()), key=lambda h: -h["eur"]),
            "next": [], "log": list(reversed(logs.get(name, [])))[:LOG_MAX],
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
            "species": species, "p": out, "dead": dead, "band": band, "luck": luck, "day": day, "fillsByDay": fills_by_day}


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


# ---------- JOURNAL: one page per night, built only from what was known that night ----------
def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (ValueError, OSError):
        return None


def journal_pages(archive, days, data):
    """The daily newspaper (Experience v2, 3.5): Markets, World, Companies, People, Arena, and a front page.
    Every item carries its source (journal fingerprint, price file, or the World Brief citations)."""
    import pandas as pd
    if not days:
        return {}
    names = {c["ticker"]: c for c in config.UNIVERSE["companies"]}
    prices = archive.read("prices")
    prices = prices[prices["date"] <= days[-1]]
    close = prices.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    ret = close.pct_change(fill_method=None)
    by_id = {p["id"]: p for p in data["p"]}
    dates = data["meta"]["dates"]
    docs = (_read_json(archive.root / "intel" / "site" / "docs.json") or {}).get("docs", {})
    alerts = (_read_json(archive.root / "intel" / "site" / "alerts.json") or {}).get("alerts", [])
    pages = {}
    for k, d in enumerate(days):
        j = archive.read_journal(d)
        path = archive.journal_path(d)
        src_journal = {"kind": "journal", "label": f"Arena journal {d}", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        src_prices = {"kind": "prices", "label": "Closing prices (Yahoo, cross-checked with Tiingo)", "sha256": (j.get("inputs") or {}).get("prices")}
        r = ret.loc[d] if d in ret.index else pd.Series(dtype=float)
        r = r[[t for t in r.index if t in names]].dropna()
        movers = [{"t": t, "name": names[t]["name"], "sector": names[t]["sector"], "ret": round(float(v), 5)}
                  for t, v in pd.concat([r.nlargest(5), r.nsmallest(5)]).items()]
        sectors = {}
        for t, v in r.items():
            sectors.setdefault(names[t]["sector"], []).append(float(v))
        sector_rows = sorted(({"sector": sct, "ret": round(sum(v) / len(v), 5), "n": len(v)} for sct, v in sectors.items()),
                             key=lambda x: -x["ret"])
        m, m0 = j.get("market") or {}, (archive.read_journal(days[k - 1]).get("market") if k else {}) or {}
        spx = round(m["sp500"] / m0["sp500"] - 1, 5) if m.get("sp500") and m0.get("sp500") else None
        fills = [{"id": _slug(n), "k": f["side"], "t": f["ticker"], "eur": f["eur"]} for n, dec in j["decisions"].items() for f in dec["fills"]]
        traded = {}
        for f in fills:
            if f["t"] in names:
                traded.setdefault(f["t"], {"t": f["t"], "name": names[f["t"]]["name"], "buys": 0, "sells": 0})["buys" if f["k"] == "buy" else "sells"] += 1
        i = dates.index(d)
        arena_moves = []
        if i > 0:
            for p in data["p"]:
                if p["type"] != "agent":
                    continue
                off = dates.index(p["from"]) if p["from"] in dates else 0
                a, b = i - off - 1, i - off
                if a >= 0 and b < len(p["s"]):
                    arena_moves.append({"id": p["id"], "name": p["name"], "ret": round(p["s"][b] / p["s"][a] - 1, 5)})
        arena_moves.sort(key=lambda x: -x["ret"])
        brief = _read_json(archive.root / "intel" / "brief" / d[:4] / f"{d}.json")
        world = None
        if brief and isinstance(brief.get("brief"), dict) and (brief["brief"].get("partial") or "invalid_json" in brief["brief"]):
            # cut-off brief: never show the raw text, only say it is incomplete today
            world = {"incomplete": True, "as_of": brief.get("as_of"), "model": brief.get("model"), "items": [], "sectors": [], "watch": []}
        elif brief and isinstance(brief.get("brief"), dict):
            b = brief["brief"]
            cite = lambda ids: [{"id": c, **({k2: docs[c].get(k2) for k2 in ("title", "url", "source", "published_at")} if c in docs else {})} for c in ids or []]
            world = {"as_of": brief.get("as_of"), "model": brief.get("model"), "headline": b.get("headline"),
                     "items": [{"topic": w.get("topic"), "summary": w.get("summary"), "cites": cite(w.get("citations"))} for w in b.get("world", [])],
                     "markets": b.get("markets"),
                     "sectors": [{"sector": x.get("sector"), "score": x.get("score"), "reason": x.get("reason"), "cites": cite(x.get("citations"))} for x in b.get("sectors", [])],
                     "watch": b.get("watch", []), "unknown_citations": brief.get("unknown_citations", [])}
        people = [a for a in alerts if str(a.get("disclosed_at", ""))[:10] == d]
        front = []
        if spx is not None:
            front.append({"k": "market", "title": f"S&P 500 {'rises' if spx >= 0 else 'falls'} (USD)", "v": spx, "src": "prices"})
        if movers:
            top = max(movers, key=lambda x: abs(x["ret"]))
            front.append({"k": "company", "title": top['name'], "t": top["t"], "v": top["ret"], "src": "prices"})
        if arena_moves:
            top = max(arena_moves, key=lambda x: abs(x["ret"]))
            front.append({"k": "arena", "title": f"{top['name']}, biggest agent move", "id": top["id"], "v": top["ret"], "src": "journal"})
        if world and world.get("headline"):
            front.insert(0, {"k": "world", "title": world["headline"], "src": "brief"})
        if people:
            front.append({"k": "people", "title": f"{len(people)} new disclosure{'s' if len(people) > 1 else ''}", "src": "alerts"})
        front.sort(key=lambda x: (x["k"] != "world", -abs(x.get("v") or 0)))
        pages[d] = {
            "date": d, "front": front[:4],
            "markets": {"spx": spx, "eurusd": m.get("eurusd"), "above_ma": m.get("above_ma"), "sectors": sector_rows, "movers": movers},
            "companies": {"traded": sorted(traded.values(), key=lambda x: -(x["buys"] + x["sells"]))[:10], "movers": movers},
            "arena": {"fills": len(fills), "buys": sum(f["k"] == "buy" for f in fills), "sells": sum(f["k"] == "sell" for f in fills),
                      "agents": len({f["id"] for f in fills}), "best": arena_moves[:3], "worst": arena_moves[-3:][::-1] if arena_moves else [],
                      "excluded": (j.get("checks") or {}).get("excluded", []), "rule_changes": j.get("rule_changes")},
            "world": world, "people": people,
            "sources": {"journal": src_journal, "prices": src_prices, **({"brief": {"kind": "brief", "label": f"World Brief ({world['model']})", "as_of": world["as_of"]}} if world else {})},
        }
    return pages


# ---------- ASK: the passages the copilot may use (and must cite) ----------
def _pct(x, d=1):
    return "n/a" if x is None else f"{x * 100:+.{d}f}%"


def corpus(data, pages):
    """Short, dated passages from the archive. The copilot retrieves from these and may only cite them;
    a passage dated after the selected day is never used (answers 'as known then')."""
    out = []
    meta = data["meta"]
    out.append({"id": "about", "d": meta.get("dayZero"), "k": "about", "title": "How the arena works",
                "text": (f"Simulated money only. Each agent starts with EUR {meta['capital']:,.0f} on the S&P 100. Decisions are taken at night "
                         "and filled at the next market open with real costs (FX 0.15%, slippage 0.05%, 15% dividend withholding). "
                         "Benchmarks: the S&P 500 with dividends in euros (the water line) and equal weight. Monkeys follow the same "
                         "rules but pick at random; the luck band is where 90% of 1,000 offline monkeys end up. Ranking score: return "
                         "over the index per unit of extra risk. Merit badge only after enough history and beating 95% of monkeys. "
                         f"Rules version {meta.get('rules')}, engine {meta.get('engine')}. Not investment advice.")})
    for sp, v in data["species"].items():
        out.append({"id": f"species:{sp}", "d": meta.get("dayZero"), "k": "species", "title": f"Species {v['label']}",
                    "text": f"{v['label']} ({v['family']}): {v['about']}.", "ref": {"species": sp}})
    upd = meta.get("updated")
    agents = [p for p in data["p"] if p["type"] == "agent"]
    if agents:
        moved = any(abs(p["ret"] or 0) > 1e-6 for p in agents)
        ranked = sorted(agents, key=lambda p: -(p["score"] if p["score"] is not None else (p["vsIdx"] or 0)))
        idx = next((p for p in data["p"] if p["type"] == "index"), None)
        luck = data.get("luck") or {}
        if moved:
            txt = (f"Ranking, leader and podium as of {upd} (ranked by {'score' if all(p['score'] is not None for p in agents) else 'return versus the S&P 500'}): "
                   + "; ".join(f"{k + 1}. {p['name']} return {_pct(p['ret'])}, versus index {_pct(p['vsIdx'])}" for k, p in enumerate(ranked[:5]))
                   + f". Last: {ranked[-1]['name']} {_pct(ranked[-1]['vsIdx'])} versus index. S&P 500 since day zero {_pct(idx['ret'] if idx else None)}. "
                   + f"Agents above the S&P 500: {sum(1 for p in agents if (p['vsIdx'] or 0) > 0)} of {len(agents)}."
                   + (f" Agents above the luck band (better than 95% of {luck.get('n')} random monkeys): {sum(1 for p in agents if luck.get('p95') is not None and (p['ret'] or 0) > luck['p95'])}." if luck.get("p95") is not None else "")
                   + " Badges: " + ("merit for " + ", ".join(p["name"] for p in agents if p.get("merit")) if any(p.get("merit") for p in agents) else "all provisional") + ".")
        else:
            txt = (f"Ranking, leader and podium as of {upd}: nobody leads yet. All {len(agents)} agents start at EUR {meta['capital']:,.0f}; "
                   "the first trades happen at the next market open, so every agent is level with the S&P 500.")
        out.append({"id": "standings", "d": upd, "k": "standings", "title": "Standings: ranking, leader, podium", "text": txt, "ref": {"lens": "arena"}})
    for p in data["p"] + data.get("dead", []):
        name = p["name"]
        txt = (f"{name} ({p['type']}{', species ' + data['species'].get(p['sp'] or '', {}).get('label', '') if p['sp'] else ''}). "
               f"As of {upd}: value EUR {p['value']:,.0f}, return {_pct(p['ret'])}, versus S&P 500 {_pct(p['vsIdx'])}, "
               f"worst drop {_pct(-p['mdd'] if p['mdd'] else 0)}, fees EUR {p['fees']:,.0f}, holdings {len(p['hold'])}, cash EUR {p['cash']:,.0f}.")
        if p.get("pctAll") is not None:
            txt += f" Beats {p['pctAll'] * 100:.0f}% of 1,000 random monkeys."
        if p.get("score") is not None:
            txt += f" Ranking score {p['score']:.2f}."
        if p.get("dna"):
            w = {k: v for k, v in p["dna"]["w"].items() if v}
            txt += " DNA weights: " + ", ".join(f"{SIGNAL_LABEL.get(k, k)} {v}%" for k, v in w.items()) + f"; {p['dna'].get('picks')} stocks, review every {p['dna'].get('review')} days."
        if p.get("copies"):
            txt += f" Copies the management rules of {p['copies']} but picks at random."
        if p.get("dead"):
            dd = p["dead"]
            txt += f" In the graveyard: died {dd.get('died')}, ranked {dd.get('rank')} of {dd.get('of')} at evaluation {dd.get('evaluation')}."
        if p["hold"]:
            txt += " Top holdings: " + ", ".join(f"{h['t']} {h['w'] * 100:.0f}%" for h in p["hold"][:5]) + "."
        out.append({"id": f"p:{p['id']}", "d": upd, "k": "participant", "title": name, "text": txt, "ref": {"open": p["id"]}})
        for k, l in enumerate(p["log"]):
            if l["k"] not in ("buy", "sell"):
                continue
            out.append({"id": f"m:{p['id']}:{l['d']}:{l['t']}:{k}", "d": l["d"], "k": "decision", "title": f"{name} {l['k']} {l['t']} on {l['d']}",
                        "text": f"{name} {'bought' if l['k'] == 'buy' else 'sold'} {l['t']} for EUR {l['eur']:,.0f} at the open of {l['d']} "
                                f"(decided the night of {l.get('dd') or 'n/a'}). Reason: {l.get('why') or 'n/a'}",
                        "ref": {"open": p["id"], "date": l["d"]}})
    for d, pg in pages.items():
        m = pg["markets"]
        txt = f"Day {d}: S&P 500 (USD) {_pct(m['spx'], 2)}; EUR/USD {m['eurusd']}; S&P 500 {'above' if m['above_ma'] else 'below'} its 200-day average."
        if m["sectors"]:
            txt += f" Best sector {m['sectors'][0]['sector']} {_pct(m['sectors'][0]['ret'], 2)}, worst {m['sectors'][-1]['sector']} {_pct(m['sectors'][-1]['ret'], 2)}."
        if m["movers"]:
            txt += " Biggest company moves: " + ", ".join(f"{x['t']} {_pct(x['ret'])}" for x in sorted(m["movers"], key=lambda x: -abs(x["ret"]))[:4]) + "."
        a = pg["arena"]
        txt += f" Arena: {a['buys']} buys and {a['sells']} sells by {a['agents']} agents at the open."
        if a["best"]:
            txt += f" Best agent of the day {a['best'][0]['name']} {_pct(a['best'][0]['ret'], 2)}; worst {a['worst'][0]['name']} {_pct(a['worst'][0]['ret'], 2)}."
        out.append({"id": f"day:{d}", "d": d, "k": "day", "title": f"Journal {d}", "text": txt, "ref": {"date": d, "lens": "journal"}})
        w = pg.get("world")
        if w:
            for j, it in enumerate(w["items"]):
                out.append({"id": f"world:{d}:{j}", "d": d, "k": "world", "title": it.get("topic") or "World",
                            "text": f"World Brief {d} ({w['model']}): {it.get('summary')}",
                            "cites": [c.get("url") for c in it.get("cites", []) if c.get("url")][:3], "ref": {"date": d, "lens": "journal"}})
        for j, al in enumerate(pg.get("people") or []):
            out.append({"id": f"people:{d}:{j}", "d": d, "k": "people", "title": f"Disclosure {al.get('person_name')} {al.get('ticker')}",
                        "text": f"{al.get('person_name')} ({al.get('role') or al.get('kind')}) disclosed a {al.get('action')} of {al.get('ticker')} "
                                f"traded {al.get('traded_on')}, disclosed {str(al.get('disclosed_at'))[:10]} ({al.get('delay_days')} days later). A pattern worth noting, not an accusation.",
                        "ref": {"date": d, "lens": "journal"}})
    return {"generated": upd, "passages": out}
