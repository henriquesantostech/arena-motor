"""Federal Register API: rules, proposed rules, notices and presidential documents (executive orders, tariffs,
export controls), plus the Public Inspection desk (documents seen the business day before publication).

PIT: documents = publication date 06:00 New York (the daily issue goes online at 6 a.m.); public inspection
items = their filing time. Public domain.
"""
from datetime import date, timedelta

from .. import http
from ..store import stable_id
from ..wkb import iso, ny_to_utc

SOURCE_ID = "federal_register"
API = "https://www.federalregister.gov/api/v1/"
FIELDS = ["document_number", "title", "type", "abstract", "publication_date", "agencies", "html_url",
          "executive_order_number", "significant", "topics", "action"]
# Agencies whose documents most often move listed companies (others are kept only if they mention one).
KEY_AGENCIES = {
    "Executive Office of the President", "Bureau of Industry and Security", "International Trade Administration",
    "Office of the United States Trade Representative", "Food and Drug Administration",
    "Securities and Exchange Commission", "Federal Reserve System", "Federal Communications Commission",
    "Federal Trade Commission", "Energy Department", "Environmental Protection Agency",
    "Centers for Medicare & Medicaid Services", "Treasury Department", "Defense Department",
    "Federal Energy Regulatory Commission", "Commerce Department", "Foreign Assets Control Office",
    "Comptroller of the Currency", "Consumer Financial Protection Bureau", "Federal Aviation Administration",
    "National Highway Traffic Safety Administration", "U.S. Customs and Border Protection",
}


def _agencies(d):
    out = set()
    for a in d.get("agencies") or []:
        out.add(a.get("name") or a.get("raw_name") or "")
    for a in d.get("agency_names") or []:
        out.add(a)
    out.discard("")
    return out


def _keep(doc, linked):
    return bool(linked) or doc.get("type") == "Presidential Document" or bool(_agencies(doc) & KEY_AGENCIES)


def _documents(ctx, day):
    n = 0
    page_url = f"{API}documents.json"
    params = [("per_page", "200"), ("conditions[publication_date][is]", day), ("order", "oldest")] + \
             [("fields[]", f) for f in FIELDS]
    while page_url:
        r, sha, path = http.fetch(ctx.store, SOURCE_ID, page_url, params=params)
        js = r.json()
        docs = []
        for d in js.get("results", []):
            linked = ctx.linker.link_text(f"{d.get('title', '')} {d.get('abstract') or ''}")
            if not _keep(d, linked):
                continue
            docs.append({"doc_id": f"fr:{d['document_number']}", "source_id": SOURCE_ID,
                         "kind": f"fedreg:{(d.get('type') or 'other').lower().replace(' ', '_')}",
                         "url": d.get("html_url"), "title": (d.get("title") or "")[:300],
                         "published_at": ny_to_utc(d["publication_date"], "06:00:00"), "recorded_at": ctx.now,
                         "entity_ids": linked, "lang": "en", "text_sha": sha, "raw_path": path,
                         "extra": {"agencies": sorted(_agencies(d)), "eo": d.get("executive_order_number"),
                                   "significant": d.get("significant"), "action": d.get("action")}})
        n += ctx.store.add("documents", docs)
        page_url, params = js.get("next_page_url"), None
        if ctx.out_of_time():
            break
    return n


def _public_inspection(ctx):
    r, sha, path = http.fetch(ctx.store, SOURCE_ID, f"{API}public-inspection-documents/current.json")
    docs = []
    for d in r.json().get("results", []):
        linked = ctx.linker.link_text(f"{d.get('title', '')}")
        if not _keep(d, linked):
            continue
        pub = _when(d.get("filed_at") or d.get("public_inspection_issue_date") or ctx.now)
        docs.append({"doc_id": f"frpi:{d.get('document_number') or stable_id(d.get('title'))}", "source_id": SOURCE_ID,
                     "kind": "fedreg:public_inspection", "url": d.get("html_url") or d.get("pdf_url"),
                     "title": (d.get("title") or "")[:300], "published_at": min(pub, ctx.now), "recorded_at": ctx.now,
                     "entity_ids": linked, "lang": "en", "text_sha": sha, "raw_path": path,
                     "extra": {"agencies": sorted(_agencies(d)), "type": d.get("type"),
                               "publication_date": d.get("publication_date")}})
    return ctx.store.add("documents", docs)


def _when(s):
    """Federal Register times carry an offset; naive times and bare dates are New York time."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    s = str(s)
    if "T" not in s:
        return ny_to_utc(s[:10], "08:45:00")   # public inspection opens 8:45 a.m.
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("America/New_York"))
    return iso(dt)


def ingest(ctx):
    cursor = ctx.store.state("fedreg_cursor", None)
    today = date.fromisoformat(ctx.now[:10])
    start = date.fromisoformat(ctx.backfill_from) if ctx.backfill_from else (
        date.fromisoformat(cursor) + timedelta(days=1) if cursor else today - timedelta(days=3))
    n, d = 0, start
    while d <= today and not ctx.out_of_time():
        n += _documents(ctx, d.isoformat())
        d += timedelta(days=1)
    ctx.store.set_state("fedreg_cursor", (d - timedelta(days=1)).isoformat())
    return {"documents": n, "public_inspection": _public_inspection(ctx)}


def backfill(ctx):
    return ingest(ctx)
