"""US Treasury daily par yield curve (official, public domain). One XML feed per month.

PIT: the curve for day D is published after the close (normally by 18:00 New York); revisions are rare and are
stored as new rows dated when we saw them.
"""
import re
from datetime import date

from .. import http
from .common import add_observations

SOURCE_ID = "us_treasury"
URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
TENORS = {"BC_1MONTH": "1m", "BC_1_5MONTH": "1.5m", "BC_2MONTH": "2m", "BC_3MONTH": "3m", "BC_6MONTH": "6m", "BC_1YEAR": "1y", "BC_2YEAR": "2y",
          "BC_5YEAR": "5y", "BC_10YEAR": "10y", "BC_20YEAR": "20y", "BC_30YEAR": "30y"}


def _months(ctx):
    today = date.fromisoformat(ctx.now[:10])
    start = date.fromisoformat(ctx.backfill_from) if ctx.backfill_from else (
        today.replace(day=1) if today.day > 5 else date(today.year - (today.month == 1), (today.month - 2) % 12 + 1, 1))
    y, m = start.year, start.month
    while (y, m) <= (today.year, today.month):
        yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def ingest(ctx):
    n = 0
    for ym in _months(ctx):
        r, sha, _ = http.fetch(ctx.store, SOURCE_ID, URL,
                               params={"data": "daily_treasury_yield_curve", "field_tdr_date_value_month": ym})
        rows = []
        for entry in re.findall(rb"<m:properties>(.*?)</m:properties>", r.content, re.S):
            d = re.search(rb"<d:NEW_DATE[^>]*>(\d{4}-\d{2}-\d{2})", entry)
            if not d:
                continue
            day = d.group(1).decode()
            for tag, tenor in TENORS.items():
                v = re.search(rb"<d:" + tag.encode() + rb"[^>/]*>([-0-9.]+)<", entry)
                if v:
                    rows.append({"series_id": f"ust:{tenor}", "entity_id": "country:US", "obs_date": day,
                                 "value": float(v.group(1))})
        n += add_observations(ctx, rows, SOURCE_ID, sha)
    return {"observations": n}


def backfill(ctx):
    return ingest(ctx)
