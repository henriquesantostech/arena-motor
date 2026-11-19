"""BLS (CPI, payrolls, wages, PPI, JOLTS) and BEA (GDP, PCE) official APIs.

The APIs carry no publication timestamp, so the honest PIT is the first time we saw each value
(published_at = recorded_at of the first sighting; not pit_trusted). ALFRED gives vintaged history for the same
concepts; BLS/BEA are kept as the primary official record and a cross-check.
BLS works without a key at low limits (25 queries/day); BLS_KEY raises them. BEA needs BEA_KEY.
Terms: BLS asks to cite the retrieval date and that "BLS.gov cannot vouch for the data or analyses derived from
these data after the data have been retrieved from BLS.gov"; BEA asks for citation.
"""
from datetime import date

from .. import http
from .common import add_observations

SOURCE_ID = "bls_bea"
BLS_SERIES = {"CUUR0000SA0": "cpi", "CUUR0000SA0L1E": "cpi_core", "CES0000000001": "payrolls",
              "LNS14000000": "unemployment", "CES0500000003": "avg_hourly_earnings", "WPUFD4": "ppi_final_demand",
              "JTS000000000000000JOL": "job_openings"}


def _bls(ctx):
    y = int(ctx.now[:4])
    body = {"seriesid": list(BLS_SERIES), "startyear": str(y - 1), "endyear": str(y)}
    if ctx.key("BLS_KEY"):
        body["registrationkey"] = ctx.key("BLS_KEY")
    r = http.session().post("https://api.bls.gov/publicAPI/v2/timeseries/data/", json=body, timeout=60)
    r.raise_for_status()
    sha, _ = ctx.store.put_raw(SOURCE_ID, "https://api.bls.gov/publicAPI/v2/timeseries/data/", r.content,
                               r.headers.get("Content-Type", ""))
    rows = []
    for s in r.json().get("Results", {}).get("series", []):
        for d in s.get("data", []):
            if not d.get("period", "").startswith("M") or d["period"] == "M13" or d.get("value") in ("-", ""):
                continue
            rows.append({"series_id": f"bls:{BLS_SERIES.get(s['seriesID'], s['seriesID'])}", "entity_id": "country:US",
                         "obs_date": f"{d['year']}-{d['period'][1:]}-01", "value": float(d["value"]),
                         "published_at": ctx.now})
    return add_observations(ctx, rows, SOURCE_ID, sha)


def _bea(ctx):
    key = ctx.key("BEA_KEY")
    if not key:
        return 0
    y = int(ctx.now[:4])
    r, sha, _ = http.fetch(ctx.store, SOURCE_ID, "https://apps.bea.gov/api/data",
                           params={"UserID": key, "method": "GetData", "datasetname": "NIPA", "TableName": "T10101",
                                   "Frequency": "Q", "Year": f"{y - 1},{y}", "ResultFormat": "JSON"})
    res = r.json().get("BEAAPI", {}).get("Results", {})
    err = res.get("Error") if isinstance(res, dict) else None
    if err:   # e.g. code 4 "UserId is not active": say so in the night report instead of a silent 0
        raise RuntimeError(f"BEA error {err.get('APIErrorCode')}: {str(err.get('APIErrorDescription'))[:120]}")
    rows = []
    for d in res.get("Data", []):
        if d.get("LineNumber") not in ("1", "2"):   # 1 = real GDP growth, 2 = personal consumption
            continue
        q = d["TimePeriod"]
        month = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}[q[-2:]]
        rows.append({"series_id": f"bea:gdp_line{d['LineNumber']}", "entity_id": "country:US",
                     "obs_date": f"{q[:4]}-{month}-01", "value": float(d["DataValue"].replace(",", "")),
                     "published_at": ctx.now})
    return add_observations(ctx, rows, SOURCE_ID, sha)


def ingest(ctx):
    # BLS keyless allowance is 25 queries/day: one query per night is enough.
    out = {"bls": 0, "bea": 0}
    if date.fromisoformat(ctx.now[:10]).weekday() < 6:
        out["bls"] = _bls(ctx)
    try:
        out["bea"] = _bea(ctx)
    except RuntimeError as e:
        out["bea"], out["bea_error"] = 0, str(e)
    return out
