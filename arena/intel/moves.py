""""Why did it move today?" (Experience v3 section 7): one plain-language story per company for the latest session.

Built only from stored facts, never from a language model, so it cannot invent a cause:
  - the day's return against the equal-weight universe and the company's sector, and how unusual it was
    (in units of the company's own 60-day daily volatility);
  - what was published between the previous close and this close: results and other 8-K items, linked news
    headlines (with the LLM reader's one-line summary when there is one), insider and congress disclosures;
  - whether it was a CPI, payrolls or FOMC day.
When nothing company-specific was published, the story says so and attributes the move to the market or sector.

  intel/site/moves.json              latest session, for the site
  intel/moves/YYYY/YYYY-MM-DD.json   one file per session, kept (for Ask and the archive)
Citations are document ids that resolve through intel/site/docs.json. This is description, not advice.
"""
import json
import math
from datetime import date, datetime, time, timedelta

import pandas as pd

from .. import config
from ..archive import Archive, write_json
from .sources.edgar import ITEM_NAMES, NEW_YORK
from .store import utcnow
from .wkb import iso

ROUTINE_ITEMS = {"9.01", "5.07", "5.03"}


def _close_utc(day):
    return iso(datetime.combine(date.fromisoformat(day), time(16, 0), tzinfo=NEW_YORK))


def _pct(x):
    return f"{x * 100:+.1f}%"


def _mag(x):
    return f"{abs(x) * 100:.1f}%"


def _size_word(z):
    a = abs(z)
    return "an unusually large" if a >= 3 else "a large" if a >= 2 else "a normal" if a >= 0.75 else "a small"


def build(store, archive_root=None, day=None):
    archive_root = archive_root or store.root.parent
    p = Archive(archive_root).read("prices")
    tickers = config.universe_tickers()
    p = p[p["ticker"].isin(tickers)]
    close = p.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").astype(float).sort_index()
    if len(close) < 3:
        return None
    days = list(close.index)
    day = day or days[-1]
    i = days.index(day)
    prev = days[i - 1]
    rets = close.pct_change(fill_method=None)
    r = rets.loc[day]
    vol = rets.iloc[max(0, i - 60):i].std()
    market = float(r.mean())
    sectors = {c["ticker"]: c["sector"] for c in config.UNIVERSE["companies"]}
    names = {c["ticker"]: c["name"] for c in config.UNIVERSE["companies"]}
    sec_ret = r.groupby(pd.Series(sectors)).mean()

    lo, hi = _close_utc(prev), _close_utc(day)
    con = store.connect()
    docs = con.execute(f"""SELECT doc_id, kind, title, entity_ids, extra, published_at FROM documents
                           WHERE published_at > '{lo}' AND published_at <= '{hi}'
                           QUALIFY ROW_NUMBER() OVER (PARTITION BY doc_id ORDER BY recorded_at) = 1""").df()
    summ = {}
    if store.has("readings") and len(docs):
        rd = con.execute("""SELECT doc_id, output FROM readings WHERE reader = 'llm'
                            QUALIFY ROW_NUMBER() OVER (PARTITION BY doc_id ORDER BY recorded_at DESC) = 1""").df()
        summ = {x.doc_id: json.loads(x.output).get("summary", "") for x in rd.itertuples()
                if isinstance(x.output, str) and x.output.startswith("{")}
    alerts = con.execute(f"""SELECT kind, person_name, role, ticker, action, size_high, delay_days, disclosed_at FROM alerts
                             WHERE disclosed_at > '{lo}' AND disclosed_at <= '{hi}'
                             QUALIFY ROW_NUMBER() OVER (PARTITION BY alert_id ORDER BY recorded_at) = 1""").df() \
        if store.has("alerts") else pd.DataFrame()
    try:
        macro = con.execute(f"""SELECT DISTINCT split_part(value, ':', 2) AS name FROM facts
                                WHERE valid_from = '{day}' AND (
                                  (predicate IN ('release_held', 'release_scheduled') AND split_part(value, ':', 1) IN ('10', '50'))
                                  OR (predicate = 'release_held' AND split_part(value, ':', 1) = '101'))""").df()["name"].tolist()
    except Exception:
        macro = []

    by_co = {}
    for d in docs.itertuples():
        ents = json.loads(d.entity_ids) if isinstance(d.entity_ids, str) else []
        for e in ents:
            if e.startswith("co:"):
                by_co.setdefault(e[3:], []).append(d)

    out = {}
    for t in tickers:
        if t not in r.index or not (r[t] == r[t]):
            continue
        ret, sec = float(r[t]), sectors.get(t)
        s_ret = float(sec_ret.get(sec, market))
        z = ret / float(vol[t]) if vol.get(t, 0) and vol[t] == vol[t] and vol[t] > 0 else 0.0
        reasons = []
        for d in sorted(by_co.get(t, []), key=lambda d: d.published_at):
            if d.kind.startswith("filing:8-K"):
                items = (json.loads(d.extra) if isinstance(d.extra, str) else {}).get("items", [])
                useful = [x for x in items if x not in ROUTINE_ITEMS]
                if not useful:
                    continue
                if "2.02" in useful:
                    text = "Reported quarterly results"
                else:
                    text = "Filed a company update: " + ", ".join(ITEM_NAMES.get(x, x) for x in useful)
                if summ.get(d.doc_id):
                    text += f" ({summ[d.doc_id].rstrip('.')})"
                reasons.append({"text": text, "doc_id": d.doc_id, "kind": "filing"})
            elif d.kind.startswith("filing:10-"):
                reasons.append({"text": f"Filed its {d.kind.split(':')[1]} report", "doc_id": d.doc_id, "kind": "filing"})
            elif d.kind in ("news", "social:hn"):
                reasons.append({"text": "In the news: " + (summ.get(d.doc_id) or (d.title or "")[:160]),
                                "doc_id": d.doc_id, "kind": "news"})
        if len(alerts):
            for a in alerts[alerts["ticker"] == t].itertuples():
                who = "A member of Congress" if a.kind == "congress" else f"An insider ({a.role})" if a.role else "An insider"
                reasons.append({"text": f"{who} disclosed a {a.action} (made public {a.delay_days:.0f} days after the trade)",
                                "kind": "disclosure"})
        news = [x for x in reasons if x["kind"] == "news"]
        reasons = [x for x in reasons if x["kind"] != "news"] + news[:3]
        rel_m, rel_s = ret - market, ret - s_ret
        move = f"{names.get(t, t)} {'rose' if ret > 0 else 'fell' if ret < 0 else 'was flat'} {_mag(ret)} " \
               f"({_size_word(z)} move for this stock)"
        if any(x["kind"] == "filing" for x in reasons):
            why = "the day it published new information"
        elif reasons:
            why = "with some news about the company"
        elif abs(rel_s) < max(0.005, 0.5 * abs(ret)):
            why = f"in line with its sector ({sec}, {_pct(s_ret)})"
        elif abs(rel_m) < max(0.005, 0.5 * abs(ret)):
            why = f"in line with the market ({_pct(market)})"
        else:
            why = "with no company news found in our sources"
        headline = f"{move}, {why}."
        if macro and abs(market) >= 0.005:
            reasons.append({"text": f"Market-wide: {', '.join(sorted(macro))} day; the average stock moved {_pct(market)}",
                            "kind": "macro"})
        out[t] = {"say": headline, "cites": [x["doc_id"] for x in reasons if x.get("doc_id")],
                  "name": names.get(t, t), "sector": sec, "return": round(ret, 5), "market": round(market, 5),
                  "sector_return": round(s_ret, 5), "move_in_vol_units": round(z, 2), "headline": headline,
                  "reasons": reasons}
    up = int((r > 0).sum())
    n_sec_up = int((sec_ret > 0).sum())
    say = (f"The average stock {'rose' if market > 0 else 'fell'} {_mag(market)}; {up} of {int(r.notna().sum())} "
           f"companies and {n_sec_up} of {len(sec_ret)} sectors went up.")
    if macro:
        say += f" It was a {', '.join(sorted(macro))} day."
    market_story = {"say": say, "cites": [], "from": "prices"}
    bp = store.root / "brief" / day[:4] / f"{day}.json"
    if bp.exists():   # the Daily World Brief of that date (9B model, citations checked against its context)
        b = json.loads(bp.read_text(encoding="utf-8")).get("brief", {})
        if b.get("headline") and not b.get("partial"):
            market_story = {"say": say + " World news: " + b["headline"].rstrip(".") + ".",
                            "cites": sorted({c for w in b.get("world", []) for c in w.get("citations", [])})[:6],
                            "from": "prices + daily world brief"}
    return {"as_of": utcnow(), "day": day, "market": market_story, "window": {"from": lo, "to": hi},
            "macro_events": sorted(macro),
            "note": "Built from stored facts only (prices, filings, linked news, disclosures). Description, not advice.",
            "companies": out}


def run(store, archive_root=None):
    res = build(store, archive_root)
    if not res:
        return {"moves": 0}
    write_json(store.root / "site" / "moves.json", res)
    write_json(store.root / "moves" / res["day"][:4] / f"{res['day']}.json", res)
    explained = sum(1 for v in res["companies"].values() if v["reasons"])
    return {"moves": len(res["companies"]), "with_reasons": explained, "day": res["day"]}
