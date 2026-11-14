"""SEC XBRL fundamentals, point in time, via the companyconcept API (one small JSON per company and concept).

Refreshed for a company when EDGAR shows a new 10-K/10-Q (state "xbrl_due"), and for every company on the first
run. Each value keeps its filing (accn) and `filed` date, so restatements are new vintages and never overwrite
what was known before. Frames are not used: they keep only the latest filing (not point in time).

PIT: published_at = dissemination time of the accession when EDGAR gave it to us (documents table), otherwise
the filed date + 1 business day, 06:00 New York (conservative).
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .. import http
from ..entities import company_id
from ..wkb import iso
from .edgar import cik_map

SOURCE_ID = "sec_xbrl"
NEW_YORK = ZoneInfo("America/New_York")
# concept -> short name. Alternatives for the same idea share the short name; the first one a company reports wins.
CONCEPTS = [
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "revenue"),
    ("us-gaap", "Revenues", "revenue"),
    ("us-gaap", "SalesRevenueNet", "revenue"),
    ("us-gaap", "InterestAndDividendIncomeOperating", "revenue_bank"),
    ("us-gaap", "GrossProfit", "gross_profit"),
    ("us-gaap", "OperatingIncomeLoss", "operating_income"),
    ("us-gaap", "NetIncomeLoss", "net_income"),
    ("us-gaap", "EarningsPerShareDiluted", "eps_diluted"),
    ("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "operating_cash_flow"),
    ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "capex"),
    ("us-gaap", "ResearchAndDevelopmentExpense", "rnd"),
    ("us-gaap", "Assets", "assets"),
    ("us-gaap", "Liabilities", "liabilities"),
    ("us-gaap", "StockholdersEquity", "equity"),
    ("us-gaap", "LongTermDebt", "long_term_debt"),
    ("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "cash"),
    ("dei", "EntityCommonStockSharesOutstanding", "shares_outstanding"),
]
FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F"}


def _duration(start, end):
    if not start:
        return "instant"
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    for label, lo, hi in (("3m", 80, 100), ("6m", 170, 195), ("9m", 260, 285), ("12m", 350, 380)):
        if lo <= days <= hi:
            return label
    return None


def _filed_pub(filed):
    d = date.fromisoformat(filed) + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return iso(datetime.combine(d, time(6, 0), tzinfo=NEW_YORK))


def _acceptance_times(ctx):
    if not ctx.store.has("documents"):
        return {}
    df = ctx.store.read("documents", "source_id = 'sec_edgar'")
    return {d.doc_id.removeprefix("sec:"): d.published_at for d in df.itertuples()}


def refresh(ctx, ticker, cik, acc_times, cursor):
    rows, newest, have = [], cursor, set()
    for tax, concept, short in CONCEPTS:
        if short in have or ctx.out_of_time():
            continue
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{tax}/{concept}.json"
        r, sha, _ = http.fetch(ctx.store, SOURCE_ID, url, ok_404=True)
        if r.status_code != 200 or not sha:
            continue
        units = r.json().get("units", {})
        found = False
        for unit, vals in units.items():
            for v in vals:
                if v.get("form") not in FORMS or not v.get("filed"):
                    continue
                if cursor and v["filed"] <= cursor:
                    continue
                if ctx.backfill_from and v["filed"] < ctx.backfill_from:
                    continue
                dur = _duration(v.get("start"), v["end"])
                if dur is None:
                    continue
                found = True
                newest = max(newest or v["filed"], v["filed"])
                rows.append({"series_id": f"xbrl:{short}:{dur}:{unit}", "entity_id": company_id(ticker),
                             "obs_date": v["end"], "value": float(v["val"]), "vintage": v["accn"],
                             "published_at": acc_times.get(v["accn"]) or _filed_pub(v["filed"]),
                             "recorded_at": ctx.now, "source_id": SOURCE_ID, "source_hash": sha})
        if found:
            have.add(short)
    # one row per (series, obs_date, accession): a filing repeats prior periods; keep the first occurrence
    seen, out = set(), []
    for r in rows:
        k = (r["series_id"], r["obs_date"], r["vintage"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    ctx.store.add("observations", out)
    return len(out), newest


def ingest(ctx):
    ciks = cik_map(ctx)
    cursors = ctx.store.state("xbrl_cursor", {})
    due = set(ctx.store.state("xbrl_due", []))
    todo = [c["ticker"] for c in http.universe() if ciks.get(c["ticker"]) and
            (c["ticker"] in due or c["ticker"] not in cursors or ctx.backfill_from)]
    acc_times = _acceptance_times(ctx)
    n = done = 0
    for t in todo:
        if ctx.out_of_time():
            break
        k, newest = refresh(ctx, t, ciks[t], acc_times, None if ctx.backfill_from else cursors.get(t))
        n += k
        done += 1
        cursors[t] = newest or cursors.get(t) or "0000-00-00"
        due.discard(t)
    ctx.store.set_state("xbrl_cursor", cursors)
    ctx.store.set_state("xbrl_due", sorted(due))
    return {"companies": done, "observations": n, "pending": len(todo) - done}


def backfill(ctx):
    return ingest(ctx)
