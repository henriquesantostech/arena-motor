"""The two free, terms-clean social sources: Hacker News (Algolia search API) and Bluesky (Jetstream firehose).

Hacker News: stories since the last cursor that mention a universe company; stored as documents (title, points).
Bluesky: a fixed nightly listening window on the public Jetstream; we count posts with a universe $CASHTAG per
ticker (a sample, labelled as such). Post text is never stored, which also honours later deletions.

PIT: HN created_at; Bluesky counts for the window are published at the window end.
"""
import asyncio
import json
import re
import time
from datetime import datetime, timezone

from .. import http
from ..entities import company_id
from .common import add_observations

SOURCE_ID = "social"
HN = "https://hn.algolia.com/api/v1/search_by_date"
JETSTREAM = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"
WINDOW_S = 300


def _hn(ctx):
    cursor = int(ctx.store.state("hn_cursor", 0) or (time.time() - 86400))
    newest, docs = cursor, []
    for page in range(5):
        r, sha, path = http.fetch(ctx.store, SOURCE_ID, HN, params={
            "tags": "story", "numericFilters": f"created_at_i>{cursor}", "hitsPerPage": "1000", "page": str(page)})
        js = r.json()
        for h in js.get("hits", []):
            newest = max(newest, int(h["created_at_i"]))
            linked = ctx.linker.link_text(h.get("title") or "")
            if not linked:
                continue
            docs.append({"doc_id": f"hn:{h['objectID']}", "source_id": SOURCE_ID, "kind": "social:hn",
                         "url": f"https://news.ycombinator.com/item?id={h['objectID']}", "title": (h.get("title") or "")[:300],
                         "published_at": h["created_at"].replace(".000", ""), "recorded_at": ctx.now,
                         "entity_ids": linked, "lang": "en", "text_sha": sha, "raw_path": path,
                         "extra": {"points": h.get("points"), "comments": h.get("num_comments"), "link": h.get("url")}})
        if page + 1 >= js.get("nbPages", 0):
            break
    ctx.store.set_state("hn_cursor", newest)
    return ctx.store.add("documents", docs)


async def _listen(tickers, seconds):
    import websockets
    counts, total = {}, 0
    pat = re.compile(r"\$([A-Z]{1,5}(?:\.[AB])?)\b")
    end = time.monotonic() + seconds
    async with websockets.connect(JETSTREAM, max_size=2 ** 22, open_timeout=30,
                                  additional_headers={"User-Agent": http.USER_AGENT}) as ws:
        while time.monotonic() < end:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(1, end - time.monotonic()))
            except asyncio.TimeoutError:
                break
            ev = json.loads(msg)
            c = ev.get("commit") or {}
            if ev.get("kind") != "commit" or c.get("operation") != "create":
                continue
            total += 1
            for t in set(pat.findall((c.get("record") or {}).get("text", ""))):
                if t in tickers:
                    counts[t] = counts.get(t, 0) + 1
    return counts, total


def _bluesky(ctx):
    tickers = {c["ticker"] for c in http.universe()}
    start = datetime.now(timezone.utc)
    counts, total = asyncio.run(_listen(tickers, WINDOW_S))
    end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day = start.strftime("%Y-%m-%d")
    from ..store import stable_id
    sha = stable_id("bsky", end, total)
    rows = [{"series_id": "bsky:cashtag_posts_sample", "entity_id": company_id(t), "obs_date": day,
             "value": float(counts.get(t, 0)), "published_at": end} for t in sorted(tickers)]
    rows.append({"series_id": "bsky:posts_sample_total", "entity_id": "world", "obs_date": day, "value": float(total),
                 "published_at": end})
    return add_observations(ctx, rows, SOURCE_ID, sha), total


def ingest(ctx):
    out = {"hn": _hn(ctx)}
    try:
        out["bluesky_rows"], out["bluesky_posts_seen"] = _bluesky(ctx)
    except Exception as e:
        out["bluesky_error"] = type(e).__name__
    return out
