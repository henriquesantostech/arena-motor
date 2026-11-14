"""Cboe: daily put/call ratios (market statistics JSON) and VIX-family history CSVs. Cboe website terms: personal,
non-commercial use; no redistribution. PIT: day D values are posted after the close (we use 18:00 New York)."""
import csv
import io
from datetime import date, timedelta

from .. import http
from .common import add_observations

SOURCE_ID = "cboe"
PC_URL = "https://cdn.cboe.com/data/us/options/market_statistics/daily/{d}_daily_options"
VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{s}_History.csv"
RATIOS = {"TOTAL PUT/CALL RATIO": "total", "INDEX PUT/CALL RATIO": "index", "EQUITY PUT/CALL RATIO": "equity",
          "CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO": "vix", "SPX + SPXW PUT/CALL RATIO": "spx"}


def ingest(ctx):
    n = 0
    cursor = ctx.store.state("cboe_cursor", None)
    today = date.fromisoformat(ctx.now[:10])
    d = date.fromisoformat(ctx.backfill_from) if ctx.backfill_from else (
        date.fromisoformat(cursor) + timedelta(days=1) if cursor else today - timedelta(days=7))
    last_ok = cursor
    while d <= today and not ctx.out_of_time():
        if d.weekday() < 5:
            try:   # days without a file (holidays, not yet posted) answer 403 on this CDN
                r, sha, _ = http.fetch(ctx.store, SOURCE_ID, PC_URL.format(d=d.isoformat()), ok_404=True)
            except http.FetchError:
                r, sha = None, None
            if r is not None and r.status_code == 200 and sha:
                try:
                    js = r.json()
                except ValueError:
                    js = {}
                rows = [{"series_id": f"cboe:pc:{RATIOS[x['name']]}", "entity_id": "market:US",
                         "obs_date": d.isoformat(), "value": float(x["value"])}
                        for x in js.get("ratios", []) if x.get("name") in RATIOS and x.get("value")]
                if rows:
                    n += add_observations(ctx, rows, SOURCE_ID, sha)
                    last_ok = d.isoformat()
        d += timedelta(days=1)
    ctx.store.set_state("cboe_cursor", last_ok)
    since = ctx.backfill_from or (today - timedelta(days=30)).isoformat()
    for s in ("VIX", "VIX9D", "VIX3M", "VVIX"):
        try:
            r, sha, _ = http.fetch(ctx.store, SOURCE_ID, VIX_URL.format(s=s), ok_404=True)
        except http.FetchError:
            continue
        if r.status_code != 200 or not sha:
            continue
        rows = []
        for rec in csv.DictReader(io.StringIO(r.text)):
            k = {kk.strip().upper(): vv for kk, vv in rec.items()}
            parts = (k.get("DATE") or "").split("/")
            if len(parts) != 3:
                continue
            day = f"{parts[2]}-{int(parts[0]):02d}-{int(parts[1]):02d}"
            val = k.get("CLOSE") or k.get(s)
            if day >= since and val:
                rows.append({"series_id": f"cboe:{s.lower()}", "entity_id": "market:US", "obs_date": day,
                             "value": float(val)})
        n += add_observations(ctx, rows, SOURCE_ID, sha)
    return {"observations": n}


def backfill(ctx):
    return ingest(ctx)
