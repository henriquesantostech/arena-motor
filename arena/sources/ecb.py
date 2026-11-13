"""European Central Bank adapter: daily EUR/USD reference rate (public, reuse with attribution)."""
import io
import time as _time

import pandas as pd
import requests

SOURCE_ID = "ecb"
URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"


def fetch(start):
    """Columns: date, eurusd (USD per 1 EUR)."""
    from . import USER_AGENT
    for attempt in range(4):
        try:
            r = requests.get(URL, params={"startPeriod": start, "format": "csvdata"}, headers=USER_AGENT, timeout=60)
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 3:
                raise
            _time.sleep(10 * (attempt + 1))
    df = pd.read_csv(io.StringIO(r.text))
    df = df[["TIME_PERIOD", "OBS_VALUE"]].dropna()
    df.columns = ["date", "eurusd"]
    df["eurusd"] = df["eurusd"].astype(float).round(6)
    return df.reset_index(drop=True)
