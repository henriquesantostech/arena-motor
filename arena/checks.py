"""Data checks before deciding (design 3.3).

If something fails for a company, nothing is decided about it that night, and it is logged.
"""
from . import config


def check(view, universe, delisted):
    day = view.day
    excluded = {}
    today = view.tickers_on(day)
    tab = view.adjusted_close()
    events = view.events_on(day)
    with_event = set(events["ticker"]) if len(events) else set()
    for t in universe:
        if t in delisted:
            continue
        if t not in today:
            excluded[t] = "no data today"
            continue
        if t in tab.columns:
            s = tab[t].dropna()
            if len(s) >= 2 and s.index[-1] == day:
                jump = s.iloc[-1] / s.iloc[-2] - 1
                if abs(jump) > config.DATA["suspicious_jump"] and t not in with_event:
                    excluded[t] = f"{jump:+.0%} jump with no event"
    # Cross-check with Tiingo (sample stored by that night's fetch)
    crosschecked = []
    for _, r in view.tiingo.iterrows():
        c = view.close(r["ticker"], day)
        if c is None:
            continue
        diff = abs(float(r["close"]) / c - 1)
        crosschecked.append({"ticker": r["ticker"], "difference": round(diff, 5)})
        if diff > config.DATA["max_tiingo_difference"]:
            excluded[r["ticker"]] = f"Yahoo and Tiingo differ by {diff:.1%}"
    return dict(sorted(excluded.items())), crosschecked
