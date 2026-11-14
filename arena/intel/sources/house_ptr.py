"""U.S. House of Representatives periodic transaction reports (STOCK Act), from the Clerk's public site.

Each night: the yearly index zip (XML, ~70 KB) lists every filing; new PTRs (FilingType P) are downloaded as PDF
and parsed for stock transactions in universe companies. Electronic filings parse well; scanned paper filings
yield nothing and are counted as unparsed (never guessed).

Terms: 5 U.S.C. 13107 forbids commercial use, credit rating and soliciting. Personal, non-commercial research
only; this module needs legal review or a licensed source before any commercial step (design v2, section 4.4).
PIT: the filing date is a date only; published_at = next business day 06:00 New York, or the moment we first saw
the filing if that is earlier. Trades themselves can be up to 45 days older (the disclosure delay is shown).
"""
import io
import re
import zipfile
from datetime import date, datetime, time, timedelta
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from .. import http
from ..entities import company_id
from ..store import stable_id
from ..wkb import fact, iso

SOURCE_ID = "house_ptr"
VERSION = "1"
NEW_YORK = ZoneInfo("America/New_York")
BASE = "https://disclosures-clerk.house.gov/public_disc/"
TX = re.compile(r"\(([A-Z][A-Z.]{0,5})\)\s*\[(ST|OP)\]\s*(P|S \(partial\)|S|E)\s+(\d{2}/\d{2}/\d{4})\s*"
                r"(\d{2}/\d{2}/\d{4})\s*\$([\d,]+)(?:\s*-\s*\$([\d,]+))?")


def _us_date(s):
    m, d, y = map(int, s.split("/"))
    return date(y, m, d)


def _pub(filing_date, now):
    d = filing_date + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return min(iso(datetime.combine(d, time(6, 0), tzinfo=NEW_YORK)), now)


def parse_ptr(text):
    """Stock transactions from the text of an electronic PTR."""
    flat = re.sub(r"\s+", " ", text.replace("\x00", ""))
    out = []
    for m in TX.finditer(flat):
        lo = float(m.group(6).replace(",", ""))
        hi = float(m.group(7).replace(",", "")) if m.group(7) else lo
        out.append({"ticker": m.group(1), "asset_type": m.group(2),
                    "action": {"P": "buy", "E": "exchange"}.get(m.group(3), "sell"),
                    "partial": "partial" in m.group(3), "traded_on": _us_date(m.group(4)).isoformat(),
                    "notified_on": _us_date(m.group(5)).isoformat(), "size_low": lo, "size_high": hi})
    return out


def ingest(ctx):
    from pypdf import PdfReader
    universe = {c["ticker"] for c in http.universe()}
    alias = {t.replace(".", ""): t for t in universe} | {t: t for t in universe}
    year = int(ctx.now[:4])
    years = range(int(ctx.backfill_from[:4]), year + 1) if ctx.backfill_from else [year]
    seen = ctx.store.state("house_seen", {})
    n_new = n_tx = n_unparsed = 0
    for y in years:
        r, sha, _ = http.fetch(ctx.store, SOURCE_ID, f"{BASE}financial-pdfs/{y}FD.zip")
        z = zipfile.ZipFile(io.BytesIO(r.content))
        root = ET.fromstring(z.read(f"{y}FD.xml"))
        done = set(seen.get(str(y), []))
        for m in root:
            if m.findtext("FilingType") != "P":
                continue
            doc = m.findtext("DocID")
            if doc in done or ctx.out_of_time():
                continue
            fdate = _us_date(m.findtext("FilingDate"))
            if ctx.backfill_from and fdate.isoformat() < ctx.backfill_from:
                done.add(doc)
                continue
            name = " ".join(x for x in (m.findtext("First"), m.findtext("Last"), m.findtext("Suffix")) if x)
            district = m.findtext("StateDst") or ""
            pid = f"member:{stable_id(m.findtext('Last'), m.findtext('First'), district[:2])[:12]}"
            try:
                pr, psha, path = http.fetch(ctx.store, SOURCE_ID, f"{BASE}ptr-pdfs/{y}/{doc}.pdf")
            except http.FetchError:
                continue          # retried next night
            done.add(doc)
            n_new += 1
            pub = _pub(fdate, ctx.now)
            try:
                text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pr.content)).pages)
            except Exception:
                text = ""
            txs = parse_ptr(text)
            if not txs and "[ST]" not in text and "[GS]" not in text:
                n_unparsed += 1
            ctx.store.add("documents", [{"doc_id": f"house:{doc}", "source_id": SOURCE_ID, "kind": "disclosure:ptr",
                                         "url": f"{BASE}ptr-pdfs/{y}/{doc}.pdf", "title": f"PTR {name} ({district})",
                                         "published_at": pub, "recorded_at": ctx.now, "entity_ids": [pid],
                                         "lang": "en", "text_sha": psha, "raw_path": path,
                                         "extra": {"transactions": len(txs), "parsed": bool(text)}}])
            ctx.store.add("entities", [{"entity_id": pid, "kind": "member_of_congress", "name": name, "ticker": None,
                                        "cik": None, "qid": None, "aliases": [name], "recorded_at": ctx.now,
                                        "source_id": SOURCE_ID, "source_hash": sha}])
            for t in txs:
                tk = alias.get(t["ticker"])
                if not tk or t["action"] == "exchange":
                    continue
                n_tx += 1
                ctx.store.add("facts", [fact(pid, f"member_{t['action']}", object_id=company_id(tk),
                                             value_num=t["size_high"], valid_from=t["traded_on"], published_at=pub,
                                             source_id=SOURCE_ID, source_hash=psha, extractor="house.ptr_pdf",
                                             extractor_version=VERSION, confidence=0.9, recorded_at=ctx.now)])
                ctx.store.add("alerts", [{
                    "alert_id": stable_id(doc, tk, t["traded_on"], t["action"], t["size_low"]), "kind": "congress",
                    "person_id": pid, "person_name": name, "role": f"U.S. Representative ({district})", "ticker": tk,
                    "action": t["action"], "size_low": t["size_low"], "size_high": t["size_high"],
                    "traded_on": t["traded_on"], "disclosed_at": pub,
                    "delay_days": float((fdate - date.fromisoformat(t["traded_on"])).days), "recorded_at": ctx.now,
                    "source_id": SOURCE_ID, "source_hash": psha,
                    "note": ("options; " if t["asset_type"] == "OP" else "") + ("partial sale" if t["partial"] else "")}])
        seen[str(y)] = sorted(done)
    ctx.store.set_state("house_seen", {k: v for k, v in seen.items() if int(k) >= year - 1})
    return {"new_reports": n_new, "universe_transactions": n_tx, "unparsed_scans": n_unparsed}


def backfill(ctx):
    return ingest(ctx)
