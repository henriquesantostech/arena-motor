"""Measuring success (design ch. 7): profile indicators and the ranking score."""
import math

import numpy as np

from . import config

M = config.METRICS
INDEX = "S&P 500 (EUR)"


def indicators(name, series, index_series, part, monkey_series, year):
    """series: list of (date, value) since birth."""
    dates = [d for d, _ in series]
    v = np.array([x for _, x in series], dtype=float)
    base = v[0]
    ret = v[-1] / base - 1
    idx = dict(index_series)
    vi = np.array([idx.get(d, np.nan) for d in dates], dtype=float)
    idx_ret = vi[-1] / vi[0] - 1 if len(vi) and vi[0] else None
    days = len(v) - 1
    r = v[1:] / v[:-1] - 1 if days else np.array([])
    ri = vi[1:] / vi[:-1] - 1 if days else np.array([])
    vol = float(np.std(r, ddof=0) * math.sqrt(M["trading_days_per_year"])) if days > 1 else None
    peak = np.maximum.accumulate(v)
    max_dd = float(np.max(1 - v / peak)) if len(v) else 0.0
    active = r - ri
    ir = None
    if days >= M["min_days_for_score"] and np.std(active) > 0:
        ir = float(np.mean(active) / np.std(active, ddof=0) * math.sqrt(M["trading_days_per_year"]))
    sc = None
    if ir is not None:
        penalty = max(0.0, max_dd - M["max_drawdown_penalty_from"]) * M["penalty_per_point"]
        sc = ir - penalty
    t = part["totals"]
    mean_v = float(np.mean(v))
    turnover = (t["sells_eur"] / mean_v) * (M["trading_days_per_year"] / days) if days and mean_v else 0.0
    gains = t["realized_gains"].get(year, 0.0)
    beats = None
    if monkey_series and part["type"] != "monkey":
        rets = [s[-1][1] / s[0][1] - 1 for s in monkey_series.values() if s]
        beats = sum(1 for x in rets if x < ret) / len(rets) if rets else None
    return {
        "value": round(float(v[-1]), 2),
        "return": round(ret, 6),
        "index_same_period": None if idx_ret is None else round(float(idx_ret), 6),
        "vs_index": None if idx_ret is None else round(ret - float(idx_ret), 6),
        "volatility": None if vol is None else round(vol, 6),
        "max_drawdown": round(max_dd, 6),
        "costs": t["costs"],
        "dividends": t["dividends"],
        "turnover": round(turnover, 4),
        "hit_rate": None if not t["closed"] else round(t["winners"] / t["closed"], 4),
        "closed_trades": t["closed"],
        "estimated_tax": round(max(0.0, gains) * M["capital_gains_tax"], 2),
        "realized_gains_year": gains,
        "score": None if sc is None else round(sc, 4),
        "beats_monkeys": None if beats is None else round(beats, 4),
        "days": days,
    }


def label(ind, monkey_scores, merit_row=None):
    """Merit badge. From rules 1.2 (2026-11-17) badge v2 (rules/merit.json): 12 months, DSR >= 0.95, above the
    p95 of the best of 1,000 monkeys and beats the S&P 500 net of costs. Pass the agent's row of the archive's
    merit/report.json as `merit_row`; without it nobody can earn the badge. A rehearsal never earns it.
    Badge v1 could not be earned before 126 days of life, so switching now changes nothing already shown."""
    if not merit_row:
        return "provisional"
    return "merit" if merit_row.get("badge") == "merit" else "provisional"


def _label_v1(ind, monkey_scores):
    """Merit badge v1 (design 6.4): 6 months, beats the index and scores above 95% of the monkeys."""
    if ind["days"] < M["merit_min_days"]:
        return "provisional"
    if ind["vs_index"] is None or ind["vs_index"] <= 0 or ind["score"] is None:
        return "provisional"
    pm = [p for p in monkey_scores if p is not None]
    if not pm:
        return "provisional"
    above = sum(1 for p in pm if p < ind["score"]) / len(pm)
    return "merit" if above >= M["merit_monkey_percentile"] else "provisional"
