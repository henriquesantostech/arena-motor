"""FRED / ALFRED (St. Louis Fed): macro series with their vintages, and the release calendar.

Needs FRED_KEY. Every observation is stored with realtime_start as published_at, so a decision at T only sees
the value the world had at T (no revision leakage). Notice required by the terms: "This product uses the FRED®
API but is not endorsed or certified by the Federal Reserve Bank of St. Louis."
"""
from datetime import date, timedelta

from .. import http
from ..wkb import ny_to_utc
from .common import add_observations

SOURCE_ID = "fred_alfred"
API = "https://api.stlouisfed.org/fred/"
# series -> entity. Kept small and stable: the regime inputs of design v2 sections 3 and 7.1.
SERIES = {
    "CPIAUCSL": "country:US", "CPILFESL": "country:US", "PCEPILFE": "country:US", "PAYEMS": "country:US",
    "UNRATE": "country:US", "ICSA": "country:US", "GDPC1": "country:US", "INDPRO": "country:US",
    "RSAFS": "country:US", "UMCSENT": "country:US", "FEDFUNDS": "country:US", "DFF": "country:US",
    "T10Y2Y": "country:US", "T10Y3M": "country:US", "BAMLH0A0HYM2": "country:US", "DTWEXBGS": "country:US",
    "DCOILWTICO": "world", "NFCI": "country:US", "WALCL": "country:US", "M2SL": "country:US",
}


def _obs(ctx, key, sid, start):
    r, sha, _ = http.fetch(ctx.store, SOURCE_ID, f"{API}series/observations",
                           params={"series_id": sid, "api_key": key, "file_type": "json",
                                   "realtime_start": start, "realtime_end": "9999-12-31",
                                   "observation_start": (date.fromisoformat(start) - timedelta(days=800)).isoformat()})
    rows = []
    for o in r.json().get("observations", []):
        if o.get("value") in (None, ".", ""):
            continue
        rows.append({"series_id": f"fred:{sid}", "entity_id": SERIES[sid], "obs_date": o["date"],
                     "value": float(o["value"]), "vintage": o["realtime_start"],
                     "published_at": ny_to_utc(o["realtime_start"], "08:30:00")})
    return rows, sha


def _store_vintages(ctx, rows, sha):
    """ALFRED rows are already vintaged: keep one row per (series, obs_date, vintage) not stored yet."""
    if not rows:
        return 0
    have, last = set(), {}
    if ctx.store.has("observations"):
        df = ctx.store.read("observations", "series_id = ?", [rows[0]["series_id"]])
        have = {(r.obs_date, r.vintage) for r in df.itertuples()}
        for r in df.sort_values("vintage", kind="mergesort").itertuples():
            last[r.obs_date] = r.value
    # The query window starts a few days back, so ALFRED reports an older unchanged value with realtime_start = the
    # window start: a new "vintage" every night with the same value. Only a changed value is a revision.
    out = [{**r, "recorded_at": ctx.now, "source_id": SOURCE_ID, "source_hash": sha}
           for r in rows if (r["obs_date"], r["vintage"]) not in have
           and not (r["obs_date"] in last and abs(last[r["obs_date"]] - r["value"]) < 1e-12)]
    return ctx.store.add("observations", out)


def _calendar(ctx, key):
    today = date.fromisoformat(ctx.now[:10])
    r, sha, path = http.fetch(ctx.store, SOURCE_ID, f"{API}releases/dates",
                              params={"api_key": key, "file_type": "json", "realtime_start": today.isoformat(),
                                      "realtime_end": (today + timedelta(days=21)).isoformat(),
                                      "include_release_dates_with_no_data": "true", "limit": "1000"})
    from ..wkb import fact
    rows = [fact("org:FRED", "release_scheduled", value=f"{d['release_id']}:{d.get('release_name', '')}"[:200],
                 valid_from=d["date"], published_at=ctx.now, source_id=SOURCE_ID, source_hash=sha,
                 extractor="fred.calendar", extractor_version="1", recorded_at=ctx.now)
            for d in r.json().get("release_dates", [])]
    return ctx.store.add("facts", rows)


HISTORY_RELEASES = {10: "CPI", 50: "Employment Situation", 101: "FOMC Press Release"}


def _release_history(ctx, key):
    """Past dates on which CPI, payrolls and FOMC statements were actually released (with data), loaded once and
    then refreshed for the last 40 days each night. Used for the macro event-day flag."""
    done = ctx.store.state("fred_release_history", {})
    start = "2023-01-01" if not done else (date.fromisoformat(ctx.now[:10]) - timedelta(days=40)).isoformat()
    from ..wkb import fact
    have = set()
    if ctx.store.has("facts"):
        f = ctx.store.read("facts", "predicate = 'release_held'")
        have = set(zip(f["value"], f["valid_from"]))
    rows = []
    for rid, name in HISTORY_RELEASES.items():
        r, sha, _ = http.fetch(ctx.store, SOURCE_ID, f"{API}release/dates",
                               params={"api_key": key, "file_type": "json", "release_id": str(rid),
                                       "realtime_start": start, "realtime_end": ctx.now[:10],
                                       "include_release_dates_with_no_data": "false", "sort_order": "asc",
                                       "limit": "1000"})
        for d in r.json().get("release_dates", []):
            v = f"{rid}:{name}"
            if (v, d["date"]) in have or d["date"] < start:
                continue
            rows.append(fact("org:FRED", "release_held", value=v, valid_from=d["date"],
                             published_at=ny_to_utc(d["date"], "08:30:00"), source_id=SOURCE_ID, source_hash=sha,
                             extractor="fred.release_history", extractor_version="1", recorded_at=ctx.now))
    ctx.store.set_state("fred_release_history", {"loaded": True, "day": ctx.now[:10]})
    return ctx.store.add("facts", rows)


def ingest(ctx):
    key = ctx.key("FRED_KEY")
    start = ctx.backfill_from or (date.fromisoformat(ctx.now[:10]) - timedelta(days=10)).isoformat()
    n = 0
    for sid in SERIES:
        if ctx.out_of_time():
            break
        rows, sha = _obs(ctx, key, sid, start)
        n += _store_vintages(ctx, rows, sha)
    return {"observations": n, "calendar": _calendar(ctx, key), "release_history": _release_history(ctx, key)}


def backfill(ctx):
    return ingest(ctx)
