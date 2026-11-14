"""GDELT 2.0: global events (15-minute export files) aggregated per country and day, and news article titles about
universe companies (DOC API). Terms: unlimited use, including commercial, with citation and a link to
gdeltproject.org.

Raw handling: the 15-minute files (~100 KB each, ~96 a day) stay at their permanent public URLs; we archive their
SHA-256 and URL in the fetches table plus our aggregated rows, not the files themselves (they would add ~3.6 GB a
year). DOC API answers are archived as fetched.

PIT: events use the file timestamp (DATEADDED batch, UTC); daily aggregates for day D are published at the time of
D's last file (D+1 00:00 UTC). DOC articles use seendate (when GDELT saw the article).
"""
import csv
import io
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .. import http
from ..store import sha256, stable_id
from .common import add_observations

SOURCE_ID = "gdelt"
LAST = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
FILE = "http://data.gdeltproject.org/gdeltv2/{ts}.export.CSV.zip"
DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
# FIPS 10-4 country codes used by GDELT -> ISO2 for our entity ids
FIPS = {"US": "US", "CH": "CN", "RS": "RU", "UP": "UA", "IS": "IL", "IR": "IR", "TW": "TW", "IN": "IN", "JA": "JP",
        "GM": "DE", "FR": "FR", "UK": "GB", "KS": "KR", "KN": "KP", "SA": "SA", "TU": "TR", "MX": "MX", "CA": "CA",
        "BR": "BR", "EG": "EG", "SY": "SY", "VE": "VE", "PK": "PK", "IZ": "IQ", "YM": "YE", "LE": "LB"}


def _slots(start, end):
    t = start
    while t < end:
        yield t.strftime("%Y%m%d%H%M%S")
        t += timedelta(minutes=15)


def _events(ctx):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    end = now.replace(minute=now.minute - now.minute % 15)
    cursor = ctx.store.state("gdelt_cursor")
    start = datetime.strptime(cursor, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc) + timedelta(minutes=15) if cursor \
        else (end - timedelta(days=1)).replace(hour=0, minute=0)
    # aggregate complete UTC days only
    agg = defaultdict(lambda: [0, 0, 0.0, 0.0])      # (day, cc) -> events, material conflict, goldstein sum, tone sum
    slots = list(_slots(start, end.replace(hour=0, minute=0)))[:96 * 3]     # at most 3 days per night

    def get(ts):
        try:
            return ts, http.get(FILE.format(ts=ts), timeout=60, ok_404=True)
        except http.FetchError:
            return ts, None

    from concurrent.futures import ThreadPoolExecutor
    last_done, files = cursor, 0
    with ThreadPoolExecutor(max_workers=8) as pool:      # the file server is slow per request, not rate-limited
        results = list(pool.map(get, slots))
    for ts, r in results:
        if r is None:
            break                                       # keep order: stop at the first failure, retry next night
        last_done = ts
        if r.status_code != 200:
            continue
        files += 1
        ctx.store.add("fetches", [{"fetch_id": sha256(r.content), "source_id": SOURCE_ID, "url": FILE.format(ts=ts),
                                   "fetched_at": ctx.now, "status": "by_reference", "bytes": float(len(r.content)),
                                   "path": None, "content_type": "application/zip"}])
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            data = z.read(z.namelist()[0]).decode("utf-8", "ignore")
        day = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
        for row in csv.reader(io.StringIO(data), delimiter="\t"):
            if len(row) < 61:
                continue
            cc = FIPS.get(row[53])                     # ActionGeo_CountryCode
            if not cc:
                continue
            a = agg[(day, cc)]
            a[0] += 1
            a[1] += row[29] == "4"                     # QuadClass 4 = material conflict
            a[2] += float(row[30] or 0)                # GoldsteinScale
            a[3] += float(row[34] or 0)                # AvgTone
    complete = {f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" for ts in slots if ts <= (last_done or "") and ts.endswith("234500")}
    rows = []
    for (day, cc), (n, conflict, gold, tone) in agg.items():
        if day not in complete:
            continue
        nxt = (datetime.fromisoformat(day) + timedelta(days=1)).strftime("%Y-%m-%dT00:15:00Z")
        for sid, v in (("events", n), ("conflict_share", conflict / n), ("goldstein", gold / n), ("tone", tone / n)):
            rows.append({"series_id": f"gdelt:{sid}", "entity_id": f"country:{cc}", "obs_date": day,
                         "value": round(float(v), 6), "published_at": nxt})
    # the cursor only moves by whole days, so a day is always aggregated from all its 96 files
    whole = [ts for ts in slots if ts <= (last_done or "") and ts.endswith("234500")]
    if whole:
        ctx.store.set_state("gdelt_cursor", whole[-1])
    return add_observations(ctx, rows, SOURCE_ID, stable_id(SOURCE_ID, last_done)), files


def _news(ctx):
    from .. import http as h
    names = []
    for c in h.universe():
        from ..entities import EXTRA_ALIASES, base_name
        names.append((EXTRA_ALIASES.get(c["ticker"]) or [base_name(c["name"])])[0])
    names = sorted(set(names))
    n = 0
    for i in range(0, len(names), 10):
        if ctx.out_of_time():
            break
        q = "(" + " OR ".join(f'"{x}"' for x in names[i:i + 10]) + ") sourcelang:english"
        try:
            r, sha, path = http.fetch(ctx.store, SOURCE_ID, DOC, params={"query": q, "mode": "artlist", "format": "json",
                                                                       "maxrecords": "250", "timespan": "1d",
                                                                       "sort": "datedesc"})
            arts = r.json().get("articles", [])
        except (http.FetchError, ValueError):
            continue
        docs = []
        for a in arts:
            seen = a.get("seendate", "")
            if len(seen) < 15:
                continue
            pub = f"{seen[:4]}-{seen[4:6]}-{seen[6:8]}T{seen[9:11]}:{seen[11:13]}:{seen[13:15]}Z"
            linked = ctx.linker.link_text(a.get("title", ""))
            if not linked:
                continue
            docs.append({"doc_id": f"gdelt:{stable_id(a.get('url'))}", "source_id": SOURCE_ID, "kind": "news",
                         "url": a.get("url"), "title": (a.get("title") or "")[:300], "published_at": min(pub, ctx.now),
                         "recorded_at": ctx.now, "entity_ids": linked, "lang": "en", "text_sha": sha, "raw_path": path,
                         "extra": {"domain": a.get("domain"), "country": a.get("sourcecountry")}})
        seen_ids = set(ctx.store.state("gdelt_news_seen", []))
        fresh = [d for d in docs if d["doc_id"] not in seen_ids]
        ctx.store.set_state("gdelt_news_seen", sorted(seen_ids | {d["doc_id"] for d in fresh})[-5000:])
        n += ctx.store.add("documents", fresh)
    return n


def ingest(ctx):
    obs, files = _events(ctx)
    return {"event_files": files, "country_observations": obs, "news": _news(ctx)}
