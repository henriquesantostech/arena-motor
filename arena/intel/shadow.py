"""Shadow signals (pre-registered in rules/signals_shadow.json). They are written to the signals table and never
reach an agent's decision; only the Signal Lab can admit one.

For a trading day D, a signal uses only rows with published_at <= decision_cutoff(D) (end of D, New York).
Rows computed on the night itself are "live" evidence; rows computed later from backfilled, PIT-trusted sources
are "rehearsal" and are labelled as such by the lab (it compares recorded_at with the cutoff).
"""
import json
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .. import config
from ..archive import Archive
from .store import utcnow
from .wkb import decision_cutoff, info_cutoff, signal_days

NEGATIVE_8K = {"2.05", "2.06", "4.02", "3.01", "1.05", "4.01"}


def preregistered():
    return json.loads((config.RULES_DIR / "signals_shadow.json").read_text(encoding="utf-8"))["signals"]


def trading_days(archive_root):
    p = Archive(archive_root).read("prices")
    return sorted(p.loc[p["ticker"] == config.INDEX_PRICE, "date"].unique().tolist())


def _latest(df, cutoff):
    """Latest vintage per (entity, series, obs_date) among rows published by the cutoff."""
    d = df[df["published_at"] <= cutoff]
    if not len(d):
        return d
    return d.sort_values(["published_at", "recorded_at"], kind="mergesort").drop_duplicates(
        ["entity_id", "series_id", "obs_date"], keep="last")


def _dur(series_id):
    return series_id.split(":")[2]


def _ytd_ttm(rows, today):
    """Trailing 12 months from one company's flow rows of one concept (latest vintages):
    last annual + latest year-to-date - same year-to-date one year earlier."""
    ann = rows[rows["dur"] == "12m"].sort_values("obs_date")
    if not len(ann):
        return None
    a = ann.iloc[-1]
    if (date.fromisoformat(today) - date.fromisoformat(a["obs_date"])).days > 460:
        return None
    later = rows[(rows["dur"].isin(["3m", "6m", "9m"])) & (rows["obs_date"] > a["obs_date"])]
    if not len(later):
        return float(a["value"])
    y = later.sort_values(["obs_date", "dur"]).iloc[-1]
    if y["dur"] == "3m" and len(later[later["dur"].isin(["6m", "9m"]) & (later["obs_date"] == y["obs_date"])]):
        y = later[later["obs_date"] == y["obs_date"]].sort_values("dur").iloc[-1]
    target = date.fromisoformat(y["obs_date"]) - timedelta(days=365)
    prior = rows[(rows["dur"] == y["dur"])].copy()
    prior["gap"] = prior["obs_date"].map(lambda s: abs((date.fromisoformat(s) - target).days))
    prior = prior[prior["gap"] <= 20]
    if not len(prior):
        return None
    return float(a["value"] + y["value"] - prior.sort_values("gap").iloc[0]["value"])


def _growth(rows):
    """Growth of the latest reported period versus the same period one year earlier."""
    if not len(rows):
        return None
    y = rows.sort_values(["obs_date", "dur"]).iloc[-1]
    target = date.fromisoformat(y["obs_date"]) - timedelta(days=365)
    prior = rows[rows["dur"] == y["dur"]].copy()
    prior["gap"] = prior["obs_date"].map(lambda s: abs((date.fromisoformat(s) - target).days))
    prior = prior[(prior["gap"] <= 20) & (prior["value"] > 0)]
    if not len(prior):
        return None
    return float(y["value"] / prior.sort_values("gap").iloc[0]["value"] - 1)


class Inputs:
    """Everything the shadow signals read, loaded once from the knowledge base."""

    def __init__(self, store, archive_root):
        con = store.connect()
        self.facts = con.execute("""SELECT subject_id, predicate, object_id, value, valid_from, published_at, recorded_at
                                    FROM facts WHERE op = 'assert' AND predicate IN
                                    ('insider_buy', 'insider_sell', '8k_item')""").df()
        self.alerts = con.execute("SELECT person_id, ticker, action, note, disclosed_at FROM alerts WHERE kind='insider'").df()
        self.views = con.execute("""SELECT entity_id, obs_date, value, published_at FROM observations
                                    WHERE series_id = 'wiki:pageviews'""").df()
        x = con.execute("""SELECT entity_id, series_id, obs_date, value, published_at, recorded_at FROM observations
                           WHERE series_id LIKE 'xbrl:%'""").df()
        x["concept"] = x["series_id"].str.split(":").str[1]
        x["dur"] = x["series_id"].str.split(":").str[2]
        self.xbrl = x
        # readings joined to their documents; usable from max(document published, reading recorded)
        self.readings = con.execute("""
            SELECT r.reader, r.score, r.output, d.entity_ids, d.published_at AS doc_published,
                   GREATEST(d.published_at, r.recorded_at) AS usable_at
            FROM (SELECT * FROM readings WHERE reader IN ('finbert', 'llm')
                  QUALIFY ROW_NUMBER() OVER (PARTITION BY doc_id, reader ORDER BY recorded_at) = 1) r
            JOIN (SELECT * FROM documents QUALIFY ROW_NUMBER() OVER (PARTITION BY doc_id ORDER BY recorded_at) = 1) d
            USING (doc_id)""").df()
        p = Archive(archive_root).read("prices")
        self.close = p.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")


# Rehearsal (days whose cutoff passed before we ran) may trust a document's publication date for readers that cannot
# know later events (FinBERT, trained on 2019 data). The LLM and the brief model were trained on text from after most
# of our history, so their rehearsal would leak the future: they get live rows only.
REHEARSAL_READERS = {"finbert"}


def compute_day(inp, day, tickers, cut, rehearsal=False):
    """Signals dated `day`, from information published by `cut` (see wkb.info_cutoff)."""
    out = {}
    # insiders: distinct buyers (90 days) - 0.1 x distinct discretionary sellers
    a = inp.alerts[(inp.alerts["disclosed_at"] <= cut) &
                   (inp.alerts["disclosed_at"] >= decision_cutoff((date.fromisoformat(day) - timedelta(days=90)).isoformat()))]
    if len(a):
        buys = a[a["action"] == "buy"].groupby("ticker")["person_id"].nunique()
        sells = a[(a["action"] == "sell") & (a["note"] != "10b5-1 plan")].groupby("ticker")["person_id"].nunique()
        out["intel.insider_cluster_buy_90d"] = {t: float(buys.get(t, 0) - 0.1 * sells.get(t, 0)) for t in tickers}
    # negative 8-K items in the last 10 days
    f = inp.facts[(inp.facts["predicate"] == "8k_item") & (inp.facts["published_at"] <= cut) &
                  (inp.facts["published_at"] >= decision_cutoff((date.fromisoformat(day) - timedelta(days=10)).isoformat()))]
    if len(inp.facts[inp.facts["predicate"] == "8k_item"]):
        neg = f[f["value"].isin(NEGATIVE_8K)].groupby("subject_id").size()
        out["intel.filing_negative_8k_10d"] = {t: float(neg.get(f"co:{t}", 0)) for t in tickers}
    # attention spike
    v = inp.views[inp.views["published_at"] <= cut]
    if len(v):
        spike = {}
        for eid, g in v.groupby("entity_id"):
            g = g.sort_values("obs_date")
            if len(g) < 30:
                continue
            recent, base = g["value"].iloc[-3:].mean(), g["value"].iloc[-63:-3].median()
            if base > 0 and recent > 0:
                spike[eid.removeprefix("co:")] = math.log(recent / base)
        if spike:
            out["intel.attention_spike_3d"] = {t: spike[t] for t in tickers if t in spike}
    # fundamentals
    x = _latest(inp.xbrl, cut) if len(inp.xbrl) else inp.xbrl
    if len(x):
        price = inp.close.loc[:day].iloc[-1] if len(inp.close.loc[:day]) else pd.Series(dtype=float)
        rg, ey, cp = {}, {}, {}
        for eid, g in x.groupby("entity_id"):
            t = eid.removeprefix("co:")
            rev = g[g["concept"] == "revenue"]
            if not len(rev):
                rev = g[g["concept"] == "revenue_bank"]
            gr = _growth(rev[rev["dur"] != "instant"])
            if gr is not None and abs(gr) < 5:
                rg[t] = gr
            ni = _ytd_ttm(g[g["concept"] == "net_income"], day)
            sh = g[g["concept"] == "shares_outstanding"].sort_values("obs_date")
            if ni is not None and len(sh) and t in price.index and pd.notna(price[t]) and price[t] > 0:
                mcap = float(sh.iloc[-1]["value"]) * float(price[t])
                if mcap > 0:
                    ey[t] = ni / mcap
            ocf = _ytd_ttm(g[g["concept"] == "operating_cash_flow"], day)
            assets = g[g["concept"] == "assets"].sort_values("obs_date")
            if ocf is not None and len(assets) and assets.iloc[-1]["value"] > 0:
                cp[t] = ocf / float(assets.iloc[-1]["value"])
        for sid, d in (("intel.revenue_growth_yoy", rg), ("intel.earnings_yield_ttm", ey), ("intel.cash_profitability", cp)):
            if d:
                out[sid] = {t: d[t] for t in tickers if t in d}
    # news sentiment (FinBERT, 3 days) and LLM impact (5 days)
    rd = inp.readings
    if len(rd):
        if rehearsal:
            rd = rd[rd["reader"].isin(REHEARSAL_READERS) & (rd["doc_published"] <= cut)]
        else:
            rd = rd[rd["usable_at"] <= cut]
    if len(rd):
        lo3 = decision_cutoff((date.fromisoformat(day) - timedelta(days=3)).isoformat())
        lo5 = decision_cutoff((date.fromisoformat(day) - timedelta(days=5)).isoformat())
        sent, impact = {}, {}
        for r in rd.itertuples():
            ents = [e.removeprefix("co:") for e in json.loads(r.entity_ids or "[]") if e.startswith("co:")]
            if r.reader == "finbert" and r.doc_published > lo3 and r.score == r.score:
                for t in ents:
                    sent.setdefault(t, []).append(float(r.score))
            elif r.reader == "llm" and r.doc_published > lo5 and r.output and r.output.startswith("{"):
                for c in json.loads(r.output).get("companies", []):
                    if c.get("ticker") in tickers:
                        impact[c["ticker"]] = impact.get(c["ticker"], 0.0) + c.get("direction", 0) * c.get("magnitude", 0)
        if sent:
            out["intel.news_sentiment_3d"] = {t: float(np.mean(v)) for t, v in sent.items() if t in tickers}
        if impact:
            out["intel.llm_impact_5d"] = {t: impact.get(t, 0.0) for t in tickers}
    rows = []
    for sid, vals in out.items():
        for t, val in vals.items():
            if val is not None and np.isfinite(val):
                rows.append({"date": day, "ticker": t, "signal_id": sid, "value": round(float(val), 8),
                             "published_at": cut})
    return rows


def compute_all(store, archive_root=None, start=None):
    """Live rows are computed before the decision cutoff of their day (they could have been used). Rows for days
    whose cutoff passed long ago are technical rehearsal and go to the signals_rehearsal table."""
    archive_root = archive_root or store.root.parent
    known = trading_days(archive_root)
    now = utcnow()
    days = signal_days(known, now)
    tickers = config.universe_tickers()
    done = set()
    for table in ("signals", "signals_rehearsal"):
        if store.has(table):
            s = store.read(table)
            done |= set(zip(s["date"], s["signal_id"]))
    inp = Inputs(store, archive_root)
    first = start or (days[0] if days else None)
    n_live = n_reh = 0
    for day in days:
        cut = info_cutoff(day, known)
        if day < first or cut > now:
            continue
        live = now <= decision_cutoff(day)
        rows = [r for r in compute_day(inp, day, tickers, cut, rehearsal=not live)
                if (r["date"], r["signal_id"]) not in done]
        for r in rows:
            r["recorded_at"] = now
        if live:
            n_live += store.add("signals", rows)
        else:
            n_reh += store.add("signals_rehearsal", rows)
    store.flush()
    return {"live_rows": n_live, "rehearsal_rows": n_reh}
