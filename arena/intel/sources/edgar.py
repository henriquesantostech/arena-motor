"""SEC EDGAR: filings of the universe companies (8-K items, 10-K/10-Q, Form 4, Form 144, 13D) with legal timing.

Each night, for every business day since the cursor:
  1. the EDGAR daily master index (all filings of the day; a permanent public file, kept by reference: URL + SHA-256);
  2. for universe filings of the forms we follow: the filing header (.hdr.sgml, ~2 KB: acceptance time, 8-K items),
     or for Form 4 the full submission text (~10 KB: header + ownership XML), both archived as fetched.
This keeps the archive at tens of MB a year (per-company JSON would add ~1.4 GB a year). New 10-K/10-Q trigger an
XBRL refresh (see xbrl.py). Fair access: declared User-Agent with contact, well under 10 requests per second.

PIT: the header's ACCEPTANCE-DATETIME is New York time. Filings accepted after 17:30 (22:00 for Forms 3/4/5) or on
a weekend are disseminated the next business day at 06:00 New York; published_at is the dissemination time.
"""
import re
from datetime import date, datetime, time, timedelta
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from .. import http
from ..entities import company_id
from ..store import sha256, stable_id
from ..wkb import fact, iso

SOURCE_ID = "sec_edgar"
VERSION = "2"
NEW_YORK = ZoneInfo("America/New_York")
ARCHIVES = "https://www.sec.gov/Archives/"
FORMS = {"8-K", "8-K/A", "10-K", "10-K/A", "10-Q", "10-Q/A", "4", "4/A", "144", "SC 13D", "SC 13D/A",
         "SCHEDULE 13D", "SCHEDULE 13D/A", "DEF 14A", "S-4", "425"}
ITEM_NAMES = {
    "1.01": "material agreement", "1.02": "agreement terminated", "1.03": "bankruptcy", "1.05": "cybersecurity incident",
    "2.01": "acquisition or disposal completed", "2.02": "results of operations", "2.03": "new financial obligation",
    "2.04": "obligation accelerated", "2.05": "exit or restructuring costs", "2.06": "material impairment",
    "3.01": "delisting notice", "3.02": "unregistered equity sale", "3.03": "rights of holders modified",
    "4.01": "auditor change", "4.02": "financials no longer reliable", "5.01": "change of control",
    "5.02": "director or officer change", "5.03": "bylaws amended", "5.07": "shareholder vote",
    "7.01": "Regulation FD disclosure", "8.01": "other events", "9.01": "financial statements and exhibits",
}


def cik_map(ctx):
    """ticker -> 10-digit CIK. SEC company_tickers.json first; otherwise the CIKs recorded from Wikidata
    (entities table) and the last known map."""
    cached = ctx.store.state("sec_cik_map")
    if cached and cached.get("day") == ctx.now[:10]:
        return cached["map"]
    prev = (cached or {}).get("map", {})
    by_ticker = {}
    try:
        r, sha, _ = http.fetch(ctx.store, SOURCE_ID, "https://www.sec.gov/files/company_tickers.json")
        by_ticker = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in r.json().values()}
    except http.FetchError:
        pass
    wd = {}
    if ctx.store.has("entities"):
        e = ctx.store.read("entities", "cik IS NOT NULL AND ticker IS NOT NULL")
        for row in e.sort_values("recorded_at").itertuples():
            wd[row.ticker] = str(row.cik).zfill(10)
    out = {}
    for c in http.universe():
        t = c["ticker"]
        out[t] = by_ticker.get(t) or by_ticker.get(t.replace(".", "-")) or prev.get(t) or wd.get(t)
    ctx.store.set_state("sec_cik_map", {"day": ctx.now[:10], "map": out})
    return out


def accepted_utc(s):
    """Acceptance time to ISO UTC. Header form '20261112085241' is New York time; JSON form
    '2026-11-12T23:58:20.000Z' is UTC."""
    if re.fullmatch(r"\d{14}", s):
        return iso(datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=NEW_YORK))
    s = s.replace("Z", "").split(".")[0]
    return iso(datetime.fromisoformat(s).replace(tzinfo=ZoneInfo("UTC")))


def disseminated_utc(accepted, form):
    """When the public could see the filing: acceptance time, or the next business day at 06:00 New York when
    accepted after the cut-off (17:30, or 22:00 for Forms 3/4/5) or on a weekend."""
    t = datetime.fromisoformat(accepted.replace("Z", "+00:00")).astimezone(NEW_YORK)
    cut = time(22, 0) if form.split("/")[0] in ("3", "4", "5") else time(17, 30)
    if t.weekday() < 5 and t.time() <= cut:
        return accepted
    d = t.date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return iso(datetime.combine(d, time(6, 0), tzinfo=NEW_YORK))


def parse_header(text):
    """Fields of an EDGAR SEC-HEADER block."""
    def one(tag):
        m = re.search(rf"<{tag}>([^\n<]*)", text)
        return m.group(1).strip() if m else None
    return {"accepted": one("ACCEPTANCE-DATETIME"), "accession": one("ACCESSION-NUMBER"), "type": one("TYPE"),
            "period": one("PERIOD"), "filing_date": one("FILING-DATE"),
            "items": re.findall(r"<ITEMS>([^\n<]*)", text)}


def parse_master_index(text, ciks, forms=FORMS):
    """(cik, company, form, file name) lines of the daily master index for the given CIKs and forms."""
    out = []
    for line in text.splitlines():
        p = line.split("|")
        if len(p) == 5 and p[0].isdigit() and p[0].zfill(10) in ciks and p[2] in forms:
            out.append((p[0].zfill(10), p[1], p[2], p[4]))
    return out


def _business_days(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _filing(ctx, ticker, cik, form, fname):
    """One universe filing: header (or full text for Form 4) -> document, facts, alerts. Returns counts."""
    acc = fname.rsplit("/", 1)[-1].removesuffix(".txt")
    folder = f"{ARCHIVES}edgar/data/{int(cik)}/{acc.replace('-', '')}/"
    is_f4 = form in ("4", "4/A")
    url = ARCHIVES + fname if is_f4 else f"{folder}{acc}.hdr.sgml"
    r, sha, path = http.fetch(ctx.store, SOURCE_ID, url)
    text = r.content.decode("utf-8", "ignore")
    h = parse_header(text)
    if not h["accepted"]:
        return 0, 0, 0
    accepted = accepted_utc(h["accepted"])
    pub = disseminated_utc(accepted, form)
    items = [i.strip() for i in h["items"] if i.strip()]
    name = next((c["name"] for c in http.universe() if c["ticker"] == ticker), ticker)
    ctx.store.add("documents", [{
        "doc_id": f"sec:{acc}", "source_id": SOURCE_ID, "kind": f"filing:{form}", "url": f"{folder}{acc}-index.htm",
        "title": f"{name} {form}" + (f" items {', '.join(items)}" if items else ""), "published_at": pub,
        "recorded_at": ctx.now, "entity_ids": [company_id(ticker)], "lang": "en", "text_sha": sha, "raw_path": path,
        "extra": {"accession": acc, "accepted_at": accepted, "filing_date": h["filing_date"], "items": items,
                  "period": h["period"]}}])
    rows = [fact(company_id(ticker), "filed", value=form, valid_from=pub, published_at=pub, source_id=SOURCE_ID,
                 source_hash=sha, extractor="edgar.header", extractor_version=VERSION, recorded_at=ctx.now)]
    for it in items:
        rows.append(fact(company_id(ticker), "8k_item", value=it, valid_from=pub, published_at=pub, source_id=SOURCE_ID,
                         source_hash=sha, extractor="edgar.header", extractor_version=VERSION, recorded_at=ctx.now))
    n_facts = ctx.store.add("facts", rows)
    n_tx = 0
    if is_f4:
        m = re.search(r"<XML>\s*(.*?)\s*</XML>", text, re.S)
        if m:
            n_tx = read_form4(ctx, ticker, acc, m.group(1).encode(), pub, sha)
    return 1, n_facts, n_tx


def ingest(ctx):
    store = ctx.store
    ciks = cik_map(ctx)
    by_cik = {v: k for k, v in ciks.items() if v}
    today = date.fromisoformat(ctx.now[:10])
    cursor = store.state("sec_index_cursor")
    done = set(store.state("sec_index_done", []))
    start = date.fromisoformat(ctx.backfill_from) if ctx.backfill_from else (
        date.fromisoformat(cursor) + timedelta(days=1) if cursor else today - timedelta(days=30))
    retry = [tuple(x) for x in store.state("sec_retry", [])]
    n_days = n_filings = n_facts = n_tx = 0
    todo = list(retry)
    days = list(_business_days(start, today))
    for d in days:
        if d.isoformat() in done or ctx.out_of_time():
            continue
        q = (d.month - 1) // 3 + 1
        url = f"{ARCHIVES}edgar/daily-index/{d.year}/QTR{q}/master.{d.strftime('%Y%m%d')}.idx"
        try:
            r = http.get(url, timeout=90, ok_404=True)
        except http.FetchError:
            continue
        if r.status_code != 200:
            if d < today - timedelta(days=4):
                done.add(d.isoformat())     # holiday: no index will ever exist
            continue                        # recent day not published yet: next night
        store.add("fetches", [{"fetch_id": sha256(r.content), "source_id": SOURCE_ID, "url": url, "fetched_at": ctx.now,
                               "status": "by_reference", "bytes": float(len(r.content)), "path": None,
                               "content_type": "text/plain"}])
        todo += [(by_cik[c], c, form, fname) for c, _, form, fname in parse_master_index(r.text, set(by_cik))]
        done.add(d.isoformat())
        n_days += 1
    # cursor = last day before the first business day not done yet
    new_cursor = cursor
    for d in days:
        if d.isoformat() not in done:
            break
        new_cursor = d.isoformat()
    still = []
    seen = set()
    for item in todo:
        if item[3] in seen:
            continue
        seen.add(item[3])
        if ctx.out_of_time():
            still.append(list(item))
            continue
        try:
            a, b, c = _filing(ctx, *item)
            n_filings, n_facts, n_tx = n_filings + a, n_facts + b, n_tx + c
            if item[2] in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
                due = set(store.state("xbrl_due", []))
                store.set_state("xbrl_due", sorted(due | {item[0]}))
        except (http.FetchError, ET.ParseError):
            still.append(list(item))
    if new_cursor:
        store.set_state("sec_index_cursor", new_cursor)
    store.set_state("sec_index_done", sorted(x for x in done if not new_cursor or x > new_cursor))
    store.set_state("sec_retry", still)
    return {"index_days": n_days, "filings": n_filings, "facts": n_facts, "form4_transactions": n_tx,
            "pending": len(still)}


def backfill(ctx):
    return ingest(ctx)


def _txt(el, path):
    x = el.find(path)
    return None if x is None or x.text is None else x.text.strip()


def read_form4(ctx, ticker, acc, xml_bytes, pub, sha):
    """Parses one Form 4: one fact + one alert per open-market transaction (P = purchase, S = sale)."""
    root = ET.fromstring(re.sub(rb"<\?xml[^>]*\?>", b"", xml_bytes).strip())
    owners = []
    for ro in root.findall("reportingOwner"):
        rel = ro.find("reportingOwnerRelationship")
        role = []
        if rel is not None:
            if _txt(rel, "isDirector") in ("1", "true"):
                role.append("director")
            if _txt(rel, "isOfficer") in ("1", "true"):
                role.append(_txt(rel, "officerTitle") or "officer")
            if _txt(rel, "isTenPercentOwner") in ("1", "true"):
                role.append("10% owner")
        owners.append({"cik": _txt(ro, "reportingOwnerId/rptOwnerCik"),
                       "name": _txt(ro, "reportingOwnerId/rptOwnerName"), "role": "; ".join(role) or "other"})
    plan = _txt(root, "aff10b5One") in ("1", "true")
    n = 0
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _txt(tx, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue   # grants, exercises, gifts, tax withholding are not open-market decisions
        day = _txt(tx, "transactionDate/value")
        shares = float(_txt(tx, "transactionAmounts/transactionShares/value") or 0)
        price = float(_txt(tx, "transactionAmounts/transactionPricePerShare/value") or 0)
        value = round(shares * price, 2)
        for o in owners:
            pid = f"cik:{o['cik']}"
            action = "buy" if code == "P" else "sell"
            ctx.store.add("facts", [fact(pid, f"insider_{action}", object_id=company_id(ticker), value_num=value,
                                         valid_from=day, published_at=pub, source_id=SOURCE_ID, source_hash=sha,
                                         extractor="edgar.form4", extractor_version=VERSION, recorded_at=ctx.now)])
            ctx.store.add("entities", [{"entity_id": pid, "kind": "person", "name": o["name"], "ticker": None,
                                        "cik": o["cik"], "qid": None, "aliases": [o["name"]],
                                        "recorded_at": ctx.now, "source_id": SOURCE_ID, "source_hash": sha}])
            ctx.store.add("alerts", [{
                "alert_id": stable_id(acc, o["cik"], day, code, shares, price), "kind": "insider",
                "person_id": pid, "person_name": o["name"], "role": o["role"], "ticker": ticker, "action": action,
                "size_low": value, "size_high": value, "traded_on": day, "disclosed_at": pub,
                "delay_days": _delay(day, pub), "recorded_at": ctx.now, "source_id": SOURCE_ID,
                "source_hash": sha, "note": "10b5-1 plan" if plan else ""}])
            n += 1
    return n


def _delay(traded_on, disclosed_at):
    try:
        return float((date.fromisoformat(disclosed_at[:10]) - date.fromisoformat(traded_on[:10])).days)
    except (TypeError, ValueError):
        return None
