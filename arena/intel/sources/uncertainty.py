"""Geopolitical Risk index (Caldara and Iacoviello, CC BY) and Economic Policy Uncertainty index (Baker, Bloom and
Davis, CC BY 4.0), daily US series.

Both are revised after first release (EPU rewrites its last 30 days every day; GPR's latest values are
preliminary). The adapter therefore stores our own nightly vintages: a first value is published when the file
says (EPU: the day after; GPR: its weekly Monday update) and every revision is a new row dated when we saw it.
Citation: "Caldara, D. and Iacoviello, M., Measuring Geopolitical Risk" and "Baker, Bloom and Davis,
policyuncertainty.com".
"""
import csv
import io
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .. import http
from ..wkb import iso
from .common import add_observations

SOURCE_ID = "gpr_epu"
EPU = "https://www.policyuncertainty.com/media/All_Daily_Policy_Data.csv"
GPR = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.dta"


def _epu(ctx):
    r, sha, _ = http.fetch(ctx.store, SOURCE_ID, EPU)
    since = ctx.backfill_from or (date.fromisoformat(ctx.now[:10]) - timedelta(days=60)).isoformat()
    rows = []
    for rec in csv.DictReader(io.StringIO(r.text)):
        try:
            d = date(int(rec["year"]), int(rec["month"]), int(rec["day"])).isoformat()
        except (KeyError, ValueError):
            continue
        if d >= since and rec.get("daily_policy_index"):
            nxt = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
            rows.append({"series_id": "epu:us_daily", "entity_id": "country:US", "obs_date": d,
                         "value": float(rec["daily_policy_index"]), "published_at": min(f"{nxt}T12:00:00Z", ctx.now)})
    return add_observations(ctx, rows, SOURCE_ID, sha)


def _gpr(ctx):
    """Weekly file (Mondays); fetched only when its Last-Modified changed."""
    head = http.session().head(GPR, timeout=30, allow_redirects=True)
    lm = head.headers.get("Last-Modified", "")
    if lm and lm == ctx.store.state("gpr_last_modified") and not ctx.backfill_from:
        return 0
    import pandas as pd
    r, sha, _ = http.fetch(ctx.store, SOURCE_ID, GPR, timeout=120)
    df = pd.read_stata(io.BytesIO(r.content))
    pub = iso(parsedate_to_datetime(lm)) if lm else ctx.now
    since = ctx.backfill_from or (date.fromisoformat(ctx.now[:10]) - timedelta(days=60)).isoformat()
    datecol = next(c for c in df.columns if c.lower() in ("date", "day"))
    rows = []
    for rec in df.to_dict("records"):
        d = pd.Timestamp(rec[datecol]).date().isoformat()
        if d < since:
            continue
        for col, sid in (("GPRD", "gpr:daily"), ("GPRD_ACT", "gpr:acts"), ("GPRD_THREAT", "gpr:threats")):
            v = rec.get(col)
            if v is not None and v == v:
                rows.append({"series_id": sid, "entity_id": "world", "obs_date": d, "value": float(v),
                             "published_at": min(pub, ctx.now)})
    ctx.store.set_state("gpr_last_modified", lm)
    return add_observations(ctx, rows, SOURCE_ID, sha)


def ingest(ctx):
    out = {"epu": _epu(ctx)}
    try:
        out["gpr"] = _gpr(ctx)
    except Exception as e:          # the GPR file format changes now and then; EPU must still land
        out["gpr_error"] = type(e).__name__
    return out


def backfill(ctx):
    return ingest(ctx)
