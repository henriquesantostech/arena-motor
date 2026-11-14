"""Wikimedia: daily English Wikipedia pageviews of each universe company (attention), and the Current Events
portal (a curated daily list of world events). Wikimedia REST API, declared User-Agent; data CC0 (pageviews)
and CC BY-SA (portal text, kept only in the private archive).

PIT: pageviews for day D (UTC) are published in the early hours of D+1; we use D+1 12:00 UTC, so they can first
inform the decision of trading day D+1. Pageview counts are not revised. Current Events: the page revision we
fetched, timestamped when we fetched it (the portal is edited after the fact, so only our snapshot is honest).
"""
import re
from datetime import date, timedelta

from .. import http
from ..entities import company_id
from ..wkb import facts_as_of
from .common import add_observations

SOURCE_ID = "wikipedia"
PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{t}/daily/{a}/{b}"
PARSE = "https://en.wikipedia.org/w/api.php"


def _titles(ctx):
    con = ctx.store.connect()
    f = facts_as_of(con, ctx.now, predicate="enwiki_title")
    titles = {r.subject_id: r.value for r in f.itertuples()} if len(f) else {}
    for c in http.universe():
        titles.setdefault(company_id(c["ticker"]), c["name"].replace(" ", "_"))
    return titles


def _pageviews(ctx):
    today = date.fromisoformat(ctx.now[:10])
    cursor = ctx.store.state("pageviews_cursor", None)
    start = date.fromisoformat(ctx.backfill_from) if ctx.backfill_from else (
        date.fromisoformat(cursor) + timedelta(days=1) if cursor else today - timedelta(days=10))
    end = today - timedelta(days=1)
    if start > end:
        return 0
    n = 0
    for eid, title in sorted(_titles(ctx).items()):
        if ctx.out_of_time():
            break
        url = PV.format(t=title.replace("/", "%2F"), a=start.strftime("%Y%m%d"), b=end.strftime("%Y%m%d"))
        r, sha, _ = http.fetch(ctx.store, SOURCE_ID, url, ok_404=True)
        if r.status_code != 200 or not sha:
            continue
        rows = []
        for it in r.json().get("items", []):
            d = f"{it['timestamp'][:4]}-{it['timestamp'][4:6]}-{it['timestamp'][6:8]}"
            nxt = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
            rows.append({"series_id": "wiki:pageviews", "entity_id": eid, "obs_date": d, "value": float(it["views"]),
                         "published_at": f"{nxt}T12:00:00Z" if f"{nxt}T12:00:00Z" < ctx.now else ctx.now})
        n += add_observations(ctx, rows, SOURCE_ID, sha)
    ctx.store.set_state("pageviews_cursor", end.isoformat())
    return n


def _current_events(ctx):
    """Yesterday's Current Events page (and today's so far), as documents: one per bullet line."""
    from ..store import stable_id
    n = 0
    today = date.fromisoformat(ctx.now[:10])
    for d in (today - timedelta(days=1), today):
        page = f"Portal:Current_events/{d.year}_{d.strftime('%B')}_{d.day}"
        r, sha, path = http.fetch(ctx.store, SOURCE_ID, PARSE, ok_404=True,
                                  params={"action": "parse", "page": page, "prop": "wikitext|revid", "format": "json",
                                          "formatversion": "2"})
        js = r.json() if r.status_code == 200 else {}
        text = js.get("parse", {}).get("wikitext", "")
        if not text:
            continue
        docs, topic = [], ""
        for line in text.splitlines():
            if line.startswith("'''") or (line.startswith("*") and not line.startswith("**") and "[[" in line and
                                          len(line) < 80):
                topic = re.sub(r"[\[\]'*]", "", line).split("|")[-1].strip()
                continue
            if line.startswith("**") and len(line) > 40:
                plain = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", line.lstrip("* "))
                plain = re.sub(r"\[https?://\S+ ([^\]]*)\]", "", plain)
                plain = re.sub(r"<[^>]+>|\{\{[^}]*\}\}", "", plain).strip()
                if len(plain) < 30:
                    continue
                docs.append({"doc_id": f"wce:{stable_id(d, plain[:200])}", "source_id": SOURCE_ID,
                             "kind": "world_event", "url": f"https://en.wikipedia.org/wiki/{page}",
                             "title": plain[:300], "published_at": ctx.now, "recorded_at": ctx.now,
                             "entity_ids": ctx.linker.link_text(plain), "lang": "en", "text_sha": sha,
                             "raw_path": path, "extra": {"topic": topic[:80], "event_day": d.isoformat(),
                                                         "revid": js.get("parse", {}).get("revid")}})
        seen = ctx.store.state("wce_seen", {})
        fresh = [x for x in docs if x["doc_id"] not in seen.get(d.isoformat(), [])]
        seen = {k: v for k, v in seen.items() if k >= (today - timedelta(days=2)).isoformat()}
        seen[d.isoformat()] = sorted(set(seen.get(d.isoformat(), [])) | {x["doc_id"] for x in docs})
        ctx.store.set_state("wce_seen", seen)
        n += ctx.store.add("documents", fresh)
    return n


def ingest(ctx):
    return {"pageviews": _pageviews(ctx), "world_events": _current_events(ctx)}


def backfill(ctx):
    return {"pageviews": _pageviews(ctx)}
