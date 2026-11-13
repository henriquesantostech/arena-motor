"""Price signals, computed every night for every company.

Each signal is put on the same scale (z-score: 0 = average versus the others; clipped to -3..+3).
"""
import numpy as np
import pandas as pd

from . import config


def compute(view, eligible):
    """Returns (raw, z): company × signal tables. Only eligible companies with enough history."""
    tab = view.adjusted_close()
    min_hist = config.DATA["min_history_days"]
    tab = tab.iloc[-(min_hist + 10):]
    cols = [t for t in eligible if t in tab.columns]
    tab = tab[cols]
    ok = [t for t in cols if tab[t].iloc[-min_hist:].notna().sum() >= min_hist - 5 and pd.notna(tab[t].iloc[-1])]
    tab = tab[ok].ffill()
    last = tab.iloc[-1]

    def ret(n, skip=0):
        return tab.iloc[-1 - skip] / tab.iloc[-1 - n] - 1

    daily = (tab / tab.shift(1) - 1).iloc[-63:]
    raw = pd.DataFrame({
        "mom_1m": ret(21),
        "mom_3m": ret(63),
        "mom_6m": ret(126),
        "mom_12m": ret(252, skip=21),
        "rev_1w": -ret(5),
        "rev_1m": -ret(21),
        "low_risk": -daily.std(ddof=0) * np.sqrt(252),
        "near_high": last / tab.iloc[-252:].max() - 1,
    })
    raw = raw.round(6)
    z = (raw - raw.mean()) / raw.std(ddof=0)
    z = z.clip(-3, 3).fillna(0.0).round(4)
    for s in config.SIGNALS:
        if s not in z.columns:
            z[s] = 0.0
            raw[s] = np.nan
    z = z[config.SIGNALS].sort_index()
    raw = raw[config.SIGNALS].sort_index()
    return raw, z


def score(z, weights):
    """Score = sum of signals × DNA weights (weights in %)."""
    w = pd.Series({s: weights.get(s, 0) / 100 for s in config.SIGNALS})
    return (z[config.SIGNALS] * w).sum(axis=1).round(4)


# Order used to break ties between equally large terms (e.g. 1-month trend and last month's drop are
# mirror images). Frozen with rules v1.0 so that justifications never change between versions.
DRIVER_TIE_ORDER = ["news", "near_high", "quality", "rev_1m", "rev_1w", "low_risk",
                    "mom_12m", "mom_1m", "mom_3m", "mom_6m", "value"]


def drivers(z, weights, ticker, n=3):
    """The n terms that weighed most in a company's score."""
    row = z.loc[ticker]
    order = {s: i for i, s in enumerate(DRIVER_TIE_ORDER)}
    p = [(s, weights.get(s, 0) / 100 * float(row[s]), float(row[s]), weights.get(s, 0))
         for s in config.SIGNALS if weights.get(s, 0)]
    p.sort(key=lambda x: (-abs(x[1]), order[x[0]]))
    return [{"signal": s, "z": round(zv, 2), "weight": w, "term": round(v, 3)} for s, v, zv, w in p[:n]]


def market_ok(view):
    """Brake: is the S&P 500 above its 200-day average?"""
    p = view.prices[view.prices["ticker"] == config.INDEX_PRICE]["close"]
    n = config.DATA["market_ma_days"]
    if len(p) < n:
        return True, None, None
    ma = float(p.iloc[-n:].mean())
    last = float(p.iloc[-1])
    return last >= ma, round(last, 2), round(ma, 2)
