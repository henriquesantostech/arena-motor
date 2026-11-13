"""Tiingo adapter (free account, personal use): cross-check of daily closes. Needs TIINGO_KEY."""
import os

import requests

from .. import config

SOURCE_ID = "tiingo"


def close(ticker, day, key=None):
    key = key or os.environ.get("TIINGO_KEY")
    if not key:
        return None
    from . import USER_AGENT
    url = f"https://api.tiingo.com/tiingo/daily/{config.yahoo_symbol(ticker)}/prices"
    try:
        r = requests.get(url, params={"startDate": day, "endDate": day, "token": key}, headers=USER_AGENT, timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    rows = [x for x in r.json() if x.get("date", "")[:10] == day]
    return float(rows[-1]["close"]) if rows else None
