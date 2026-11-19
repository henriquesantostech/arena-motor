"""Yahoo Finance adapter (via yfinance): daily prices and corporate actions. Personal use only."""
import logging
import time as _time

import pandas as pd

from .. import config

SOURCE_ID = "yahoo"
PRICE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]
EVENT_COLUMNS = ["date", "ticker", "type", "value"]


def fetch(tickers, start, end_incl, batch=20, attempts=4, raw_symbols=False):
    """Real daily prices (not adjusted for dividends) and events, in long format.

    Requests in batches and retries the ones that failed (network and Yahoo fail now and then).
    """
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    missing = list(tickers)
    prices, events = [], []
    for attempt in range(attempts):
        if not missing:
            break
        if attempt:
            _time.sleep(5 * attempt)
        size = batch if attempt == 0 else max(1, batch // (2 * attempt))
        received = set()
        for i in range(0, len(missing), size):
            p, e = _fetch_batch(missing[i:i + size], start, end_incl, raw_symbols)
            if len(p):
                prices.append(p)
                received |= set(p["ticker"])
            if len(e):
                events.append(e)
        missing = [t for t in missing if t not in received]
    p = pd.concat(prices, ignore_index=True) if prices else _empty(PRICE_COLUMNS)
    e = pd.concat(events, ignore_index=True) if events else _empty(EVENT_COLUMNS)
    return p, e


def _fetch_batch(tickers, start, end_incl, raw_symbols=False):
    import yfinance as yf

    symbols = {(t if raw_symbols else config.yahoo_symbol(t)): t for t in tickers}   # ETF symbols such as EUNL.DE are used as they are
    end = (pd.Timestamp(end_incl) + pd.Timedelta(days=1)).date().isoformat()
    try:
        d = yf.download(list(symbols), start=start, end=end, auto_adjust=False, actions=True,
                        progress=False, group_by="column", threads=False, timeout=30, multi_level_index=True)
    except Exception:
        return _empty(PRICE_COLUMNS), _empty(EVENT_COLUMNS)
    if d is None or d.empty:
        return _empty(PRICE_COLUMNS), _empty(EVENT_COLUMNS)
    prices, events = [], []
    for sym, t in symbols.items():
        if ("Close", sym) not in d.columns:
            continue
        sub = pd.DataFrame({
            "open": d[("Open", sym)], "high": d[("High", sym)], "low": d[("Low", sym)],
            "close": d[("Close", sym)], "volume": d[("Volume", sym)],
        }).dropna(subset=["close", "open"])
        sub = sub[(sub["close"] > 0) & (sub["open"] > 0)]
        sub.insert(0, "ticker", t)
        sub.insert(0, "date", [x.date().isoformat() for x in sub.index])
        prices.append(sub.reset_index(drop=True))
        for col, kind in (("Dividends", "dividend"), ("Stock Splits", "split")):
            if (col, sym) in d.columns:
                s = d[(col, sym)].dropna()
                s = s[s > 0]
                for x, v in s.items():
                    events.append({"date": x.date().isoformat(), "ticker": t, "type": kind, "value": float(v)})
    p = pd.concat(prices, ignore_index=True) if prices else _empty(PRICE_COLUMNS)
    p = p[p["date"] <= end_incl]
    e = pd.DataFrame(events, columns=EVENT_COLUMNS)
    e = e[e["date"] <= end_incl] if len(e) else e
    for c in ["open", "high", "low", "close"]:
        p[c] = p[c].astype(float).round(4)
    p["volume"] = p["volume"].fillna(0).astype("int64")
    return p.reset_index(drop=True), e.reset_index(drop=True)


def _empty(cols):
    return pd.DataFrame(columns=cols)
