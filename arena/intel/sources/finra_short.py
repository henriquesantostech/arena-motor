"""FINRA Reg SHO daily short-sale volume (consolidated NMS file). Public files; use with attribution, raw files
not redistributed. PIT: the file for day D is posted the evening of D (we use 18:00 New York)."""
from datetime import date, timedelta

from .. import http
from ..entities import company_id
from .common import add_observations

SOURCE_ID = "finra_short_volume"
URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"


def ingest(ctx):
    tick = {}
    for c in http.universe():
        t = c["ticker"]
        for alias in (t, t.replace(".", "/"), t.replace(".", ""), t.replace(".", " ")):
            tick[alias] = t
    cursor = ctx.store.state("finra_cursor", None)
    today = date.fromisoformat(ctx.now[:10])
    d = date.fromisoformat(ctx.backfill_from) if ctx.backfill_from else (
        date.fromisoformat(cursor) + timedelta(days=1) if cursor else today - timedelta(days=7))
    n, last_ok = 0, cursor
    while d <= today and not ctx.out_of_time():
        if d.weekday() < 5:
            r, sha, _ = http.fetch(ctx.store, SOURCE_ID, URL.format(d=d.strftime("%Y%m%d")), ok_404=True)
            if r.status_code == 200 and sha:
                rows = []
                for line in r.text.splitlines()[1:]:
                    p = line.split("|")
                    if len(p) < 5 or p[1] not in tick:
                        continue
                    short, total = float(p[2]), float(p[4])
                    if total > 0:
                        rows.append({"series_id": "finra:short_ratio", "entity_id": company_id(tick[p[1]]),
                                     "obs_date": d.isoformat(), "value": round(short / total, 6)})
                n += add_observations(ctx, rows, SOURCE_ID, sha)
                last_ok = d.isoformat()
        d += timedelta(days=1)
    ctx.store.set_state("finra_cursor", last_ok)
    return {"observations": n}


def backfill(ctx):
    return ingest(ctx)
