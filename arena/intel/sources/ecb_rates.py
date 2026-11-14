"""ECB Data Portal: euro short-term rate (€STR, daily), Euribor (monthly averages; the ECB does not publish daily
Euribor), main FX reference rates (daily). Public statistics, reuse with attribution.

PIT: €STR for day D is published at 08:00 CET on D+1; FX reference rates around 16:00 CET on D; monthly Euribor
averages a few days after month end (we use the 5th of the next month, 12:00 CET, unless seen earlier).
"""
import csv
import io
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .. import http
from ..wkb import iso
from .common import add_observations

SOURCE_ID = "ecb_rates"
BASE = "https://data-api.ecb.europa.eu/service/data/"
CET = ZoneInfo("Europe/Berlin")
SERIES = {
    "estr": ("EST/B.EU000A2X2A25.WT", "D+1 08:00"),
    "euribor:1m": ("FM/M.U2.EUR.RT.MM.EURIBOR1MD_.HSTA", "month+5"),
    "euribor:3m": ("FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA", "month+5"),
    "euribor:6m": ("FM/M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA", "month+5"),
    "euribor:12m": ("FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA", "month+5"),
    "fx:USD": ("EXR/D.USD.EUR.SP00.A", "D 16:00"),
    "fx:GBP": ("EXR/D.GBP.EUR.SP00.A", "D 16:00"),
    "fx:JPY": ("EXR/D.JPY.EUR.SP00.A", "D 16:00"),
    "fx:CNY": ("EXR/D.CNY.EUR.SP00.A", "D 16:00"),
    "fx:CHF": ("EXR/D.CHF.EUR.SP00.A", "D 16:00"),
}


def _pub(period, rule):
    if rule == "month+5":
        y, m = map(int, period.split("-"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return iso(datetime(y, m, 5, 12, 0, tzinfo=CET)), f"{period}-01"
    d = date.fromisoformat(period)
    if rule == "D+1 08:00":
        return iso(datetime.combine(d + timedelta(days=1), time(8, 0), tzinfo=CET)), period
    return iso(datetime.combine(d, time(16, 0), tzinfo=CET)), period


def ingest(ctx):
    n = 0
    start = ctx.backfill_from or (date.fromisoformat(ctx.now[:10]) - timedelta(days=100)).isoformat()
    for sid, (key, rule) in SERIES.items():
        r, sha, _ = http.fetch(ctx.store, SOURCE_ID, f"{BASE}{key}",
                               params={"format": "csvdata", "startPeriod": start[:7] if rule == "month+5" else start})
        rows = []
        for rec in csv.DictReader(io.StringIO(r.text)):
            if not rec.get("OBS_VALUE"):
                continue
            pub, obs = _pub(rec["TIME_PERIOD"], rule)
            if pub > ctx.now:
                pub = ctx.now
            rows.append({"series_id": f"ecb:{sid}", "entity_id": "region:EA", "obs_date": obs,
                         "value": float(rec["OBS_VALUE"]), "published_at": pub})
        n += add_observations(ctx, rows, SOURCE_ID, sha)
    return {"observations": n}


def backfill(ctx):
    return ingest(ctx)
