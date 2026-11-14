"""Binary events for the health-care names: FDA press releases (RSS), openFDA drug recalls (enforcement reports)
and ClinicalTrials.gov study updates sponsored by universe companies.

Terms: openFDA CC0 ("Data provided by the U.S. Food and Drug Administration"); FDA RSS public domain;
ClinicalTrials.gov public NLM data. PIT: RSS pubDate; openFDA report_date (weekly report, 18:00 New York);
ClinicalTrials.gov last update post date (date only: next day 06:00 New York, or when we saw it if earlier).
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .. import http
from ..entities import base_name, company_id
from ..store import stable_id
from ..wkb import iso, ny_to_utc
from .common import add_rss

SOURCE_ID = "health"
NEW_YORK = ZoneInfo("America/New_York")
FDA_RSS = "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml"


def _health_companies():
    return [c for c in http.universe() if c["sector"] == "Health Care"]


def _recalls(ctx):
    today = date.fromisoformat(ctx.now[:10])
    start = ctx.backfill_from or (today - timedelta(days=21)).isoformat()
    r, sha, path = http.fetch(ctx.store, SOURCE_ID, "https://api.fda.gov/drug/enforcement.json", ok_404=True,
                              params={"search": f"report_date:[{start.replace('-', '')} TO {today.strftime('%Y%m%d')}]",
                                      "limit": "1000"})
    if r.status_code != 200:
        return 0
    docs = []
    for x in r.json().get("results", []):
        linked = ctx.linker.link_text(x.get("recalling_firm", ""))
        if not linked:
            continue
        rd = x["report_date"]
        docs.append({"doc_id": f"fdarecall:{x.get('recall_number')}", "source_id": SOURCE_ID, "kind": "fda:recall",
                     "url": "https://api.fda.gov/drug/enforcement.json", "title": f"{x.get('classification')} recall: "
                     f"{(x.get('product_description') or '')[:200]}", "entity_ids": linked, "lang": "en",
                     "published_at": min(ny_to_utc(f"{rd[:4]}-{rd[4:6]}-{rd[6:]}", "18:00:00"), ctx.now),
                     "recorded_at": ctx.now, "text_sha": sha, "raw_path": path,
                     "extra": {"classification": x.get("classification"), "status": x.get("status"),
                               "reason": (x.get("reason_for_recall") or "")[:300]}})
    seen = set(ctx.store.state("fda_recalls_seen", []))
    fresh = [d for d in docs if d["doc_id"] not in seen]
    ctx.store.set_state("fda_recalls_seen", sorted(seen | {d["doc_id"] for d in fresh})[-3000:])
    return ctx.store.add("documents", fresh)


def _trials(ctx):
    cursor = ctx.store.state("ctgov_cursor", {})
    n = 0
    for c in _health_companies():
        if ctx.out_of_time():
            break
        sponsor = base_name(c["name"])
        since = ctx.backfill_from or cursor.get(c["ticker"]) or (date.fromisoformat(ctx.now[:10]) - timedelta(days=7)).isoformat()
        try:
            r, sha, path = http.fetch(ctx.store, SOURCE_ID, "https://clinicaltrials.gov/api/v2/studies", params={
                "query.spons": sponsor, "filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{since},MAX]",
                "fields": "NCTId,BriefTitle,OverallStatus,Phase,LastUpdatePostDate,LeadSponsorName",
                "pageSize": "200", "sort": "LastUpdatePostDate:desc"})
        except http.FetchError:
            continue
        newest = since
        docs = []
        for s in r.json().get("studies", []):
            ps = s.get("protocolSection", {})
            ident, status = ps.get("identificationModule", {}), ps.get("statusModule", {})
            design = ps.get("designModule", {})
            upd = status.get("lastUpdatePostDateStruct", {}).get("date")
            lead = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
            if not upd or sponsor.lower().split()[0] not in lead.lower():
                continue
            phases = design.get("phases") or []
            if not any(p in ("PHASE3", "PHASE2") for p in phases):
                continue
            newest = max(newest, upd)
            d = date.fromisoformat(upd) + timedelta(days=1)
            pub = min(iso(datetime.combine(d, time(6, 0), tzinfo=NEW_YORK)), ctx.now)
            docs.append({"doc_id": f"ctgov:{ident.get('nctId')}:{upd}", "source_id": SOURCE_ID, "kind": "trial:update",
                         "url": f"https://clinicaltrials.gov/study/{ident.get('nctId')}",
                         "title": f"{status.get('overallStatus')} {'/'.join(phases)}: {ident.get('briefTitle', '')[:220]}",
                         "published_at": pub, "recorded_at": ctx.now, "entity_ids": [company_id(c["ticker"])],
                         "lang": "en", "text_sha": sha, "raw_path": path,
                         "extra": {"status": status.get("overallStatus"), "phases": phases}})
        n += ctx.store.add("documents", docs)
        cursor[c["ticker"]] = (date.fromisoformat(newest) + timedelta(days=1)).isoformat() if docs else since
    ctx.store.set_state("ctgov_cursor", cursor)
    return n


def ingest(ctx):
    return {"fda_press": add_rss(ctx, SOURCE_ID, FDA_RSS, "fda:press", ["org:FDA"]), "recalls": _recalls(ctx),
            "trials": _trials(ctx)}


def backfill(ctx):
    return {"recalls": _recalls(ctx), "trials": _trials(ctx)}
