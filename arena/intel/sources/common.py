"""Helpers shared by adapters: observation de-duplication with honest revision timing, RSS parsing."""
import math

from ..wkb import ny_to_utc


def _s(x):
    """DuckDB/pandas give NaN for empty text; treat it as None."""
    return None if x is None or (isinstance(x, float) and x != x) else x


def add_observations(ctx, rows, source_id, sha, pub_rule=None):
    """Appends time-series observations that are new or changed.

    rows: dicts with series_id, entity_id, obs_date, value (+ optional published_at, vintage).
    A first value gets published_at from the row or pub_rule(obs_date). A changed value is a revision:
    it is stored as a new row with published_at = now (we only learned it now), never back-dated.
    """
    if not rows:
        return 0
    series = sorted({r["series_id"] for r in rows})
    known = {}
    if ctx.store.has("observations"):
        ph = ",".join("?" * len(series))
        df = ctx.store.read("observations", f"series_id IN ({ph})", series)
        if len(df):
            df = df.sort_values(["recorded_at", "published_at"], kind="mergesort")
            for r in df.itertuples():
                known[(r.series_id, _s(r.entity_id) or "", r.obs_date)] = r.value
    out = []
    for r in rows:
        v = r.get("value")
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        k = (r["series_id"], r.get("entity_id") or "", r["obs_date"])
        if k in known and abs(known[k] - float(v)) < 1e-12:
            continue
        pub = r.get("published_at") or (pub_rule(r["obs_date"]) if pub_rule else ny_to_utc(r["obs_date"], "18:00:00"))
        if k in known:
            pub = max(pub, ctx.now)    # revision: known only from now
        out.append({"series_id": r["series_id"], "entity_id": r.get("entity_id"), "obs_date": r["obs_date"],
                    "value": float(v), "vintage": r.get("vintage"), "published_at": pub, "recorded_at": ctx.now,
                    "source_id": source_id, "source_hash": sha})
        known[k] = float(v)
    return ctx.store.add("observations", out)


def add_rss(ctx, source_id, url, kind, entity_ids=None, max_items=200):
    """Archives one RSS/Atom feed and adds its new items as documents (title + link; text stays raw)."""
    import calendar
    import feedparser
    from datetime import datetime, timezone
    from .. import http
    from ..store import stable_id

    r, sha, path = http.fetch(ctx.store, source_id, url)
    feed = feedparser.parse(r.content)
    cursor_name = f"rss_{source_id}_{stable_id(url)[:8]}"
    cursor = ctx.store.state(cursor_name, "")
    newest = cursor
    docs = []
    for e in feed.entries[:max_items]:
        t = e.get("published_parsed") or e.get("updated_parsed")
        if not t:
            continue
        pub = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if pub <= cursor:
            continue
        # a feed item cannot be published after we saw it: clamp future-dated items
        pub = min(pub, ctx.now)
        newest = max(newest, pub)
        link = e.get("link", "")
        title = (e.get("title") or "").strip()
        linked = ctx.linker.link_text(f"{title} {e.get('summary', '')}") if ctx.linker else []
        docs.append({"doc_id": f"{source_id}:{stable_id(link or title, pub)}", "source_id": source_id, "kind": kind,
                     "url": link, "title": title[:300], "published_at": pub, "recorded_at": ctx.now,
                     "entity_ids": sorted(set((entity_ids or []) + linked)), "lang": "en", "text_sha": sha,
                     "raw_path": path, "extra": None})
    ctx.store.set_state(cursor_name, newest)
    return ctx.store.add("documents", docs)
