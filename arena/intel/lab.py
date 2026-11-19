"""Provisional Signal Lab report for the phase 2 shadow signals (until the phase 1 Signal Lab takes over).

For every pre-registered signal: daily cross-sectional rank IC between the signal on day D and the forward return
from the open of D+1 to the open h trading days later (split-adjusted; dividends ignored, a small bias at these
horizons), its Newey-West t-statistic (lag h-1 for overlapping returns), sign stability over 3 sub-periods, and
the admission gates of design v2 section 8.3. Two evidence modes are reported separately:
  live       the signals table: rows computed before the decision cutoff of their day
  rehearsal  the signals_rehearsal table: rows computed later from backfilled, PIT-trusted data (technical
             rehearsal; never admission evidence)
"""
import json
from datetime import datetime

import numpy as np
import pandas as pd

from .. import config
from ..archive import Archive, write_json
from .shadow import preregistered
from .store import utcnow


def forward_returns(archive_root, horizon):
    a = Archive(archive_root)
    p = a.read("prices")
    p = p[p["ticker"].isin(config.universe_tickers())]
    opens = p.pivot_table(index="date", columns="ticker", values="open", aggfunc="last").astype(float).sort_index()
    ev = a.read("events")
    splits = ev[ev["type"] == "split"]
    factor = pd.DataFrame(1.0, index=opens.index, columns=opens.columns)
    for s in splits.itertuples():   # value = new shares per old share, effective on its date
        if s.ticker in factor.columns:
            factor.loc[factor.index >= s.date, s.ticker] *= float(s.value)
    adj = opens * factor          # price per original share
    # signal on D -> buy at open D+1 -> sell at open D+1+h
    fwd = adj.shift(-(1 + horizon)) / adj.shift(-1) - 1
    return fwd


def newey_west_t(x, lag):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return None
    m = x.mean()
    e = x - m
    s = e @ e / n
    for k in range(1, min(lag, n - 1) + 1):
        w = 1 - k / (lag + 1)
        s += 2 * w * (e[k:] @ e[:-k]) / n
    return float(m / np.sqrt(s / n)) if s > 0 else None


def ic_series(sig, fwd):
    out = {}
    for day, g in sig.groupby("date"):
        if day not in fwd.index:
            continue
        r = fwd.loc[day].reindex(g["ticker"].values)
        ok = r.notna().values & g["value"].notna().values
        if ok.sum() < 20 or g["value"].values[ok].std() == 0:
            continue
        out[day] = float(pd.Series(g["value"].values[ok]).rank().corr(pd.Series(r.values[ok]).rank()))
    return pd.Series(out).sort_index()


def summarize(ics, horizon, expected_sign, gates):
    if not len(ics):
        return {"n_days": 0, "status": "no observations yet"}
    signed = ics * expected_sign
    t = newey_west_t(signed.values, max(1, horizon - 1))
    thirds = np.array_split(signed.values, 3) if len(signed) >= 3 else []
    sub = [float(np.mean(x)) for x in thirds if len(x)]
    res = {"n_days": int(len(ics)), "first": ics.index[0], "last": ics.index[-1],
           "mean_ic": round(float(ics.mean()), 4), "mean_ic_expected_direction": round(float(signed.mean()), 4),
           "ic_std": round(float(ics.std(ddof=1)), 4) if len(ics) > 1 else None,
           "newey_west_t": None if t is None else round(t, 2),
           "subperiod_mean_ic_expected_direction": [round(x, 4) for x in sub],
           "hit_rate": round(float((signed > 0).mean()), 3)}
    g_obs = res["n_days"] >= gates["min_observations"]
    g_t = t is not None and t > gates["min_newey_west_t"]
    g_sub = sum(x > 0 for x in sub) >= 2
    res["gates"] = {"enough_observations": g_obs, "t_above_threshold": g_t, "stable_sign": g_sub,
                    "controls_checked": False, "net_of_costs_checked": False}
    res["status"] = "candidate for review" if (g_obs and g_t and g_sub) else "shadow"
    return res


LIVE_ONLY = {"intel.llm_impact_5d", "intel.brief_sector_tailwind", "intel.guidance_8k_llm_10d"}


def market_flag_test(store, archive_root, gates):
    """Market-level risk flag (intel.macro_event_day): mean absolute equal-weight universe return on flagged trading
    days versus the other days. Live = dates scheduled (recorded) before the day; rehearsal = dates loaded later."""
    from .wkb import decision_cutoff
    a = Archive(archive_root)
    p = a.read("prices")
    p = p[p["ticker"].isin(config.universe_tickers())]
    close = p.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").astype(float).sort_index()
    absret = close.pct_change(fill_method=None).mean(axis=1).abs().dropna()
    con = store.connect()
    try:
        f = con.execute("""SELECT valid_from, MIN(recorded_at) AS rec FROM facts
                           WHERE (predicate IN ('release_held', 'release_scheduled') AND split_part(value, ':', 1) IN ('10', '50'))
                              OR (predicate = 'release_held' AND split_part(value, ':', 1) = '101')
                           GROUP BY 1""").df()
    except Exception:
        f = pd.DataFrame(columns=["valid_from", "rec"])
    out = {}
    for mode in ("live", "rehearsal"):
        if mode == "live":
            days = {r.valid_from for r in f.itertuples() if r.rec <= decision_cutoff(r.valid_from)}
        else:
            days = set(f["valid_from"])
        flagged = absret[absret.index.isin(days)]
        other = absret[~absret.index.isin(days)]
        if mode == "live":   # live comparison only over the period with live flags
            start = min(days) if days else None
            other = other[other.index >= start] if start else other.iloc[0:0]
        if len(flagged) < 2 or len(other) < 2:
            out[mode] = {"n_days": int(len(flagged)), "status": "no observations yet"}
            continue
        t = (flagged.mean() - other.mean()) / np.sqrt(flagged.var(ddof=1) / len(flagged) + other.var(ddof=1) / len(other))
        ratio = float(flagged.mean() / other.mean()) if other.mean() > 0 else None
        ok = len(flagged) >= 20 and ratio is not None and ratio > 1 and t > gates["min_newey_west_t"]
        out[mode] = {"n_days": int(len(flagged)), "other_days": int(len(other)),
                     "mean_abs_return_flagged": round(float(flagged.mean()), 5),
                     "mean_abs_return_other": round(float(other.mean()), 5),
                     "ratio": None if ratio is None else round(ratio, 3), "t": round(float(t), 2),
                     "status": "candidate for review" if ok else "shadow"}
    return out   # see shadow.REHEARSAL_READERS


def report(store, archive_root=None):
    archive_root = archive_root or store.root.parent
    meta = json.loads((config.RULES_DIR / "signals_shadow.json").read_text(encoding="utf-8"))
    gates = meta["gates"]
    live = store.read("signals").assign(live=True)
    reh = store.read("signals_rehearsal").assign(live=False)
    parts = [x for x in (live, reh) if len(x)]
    sig = pd.concat(parts, ignore_index=True) if parts else live
    out = {"generated_at": utcnow(), "note": __doc__.strip().splitlines()[0], "signals": {}}
    fwd_cache = {}
    for p in preregistered():
        h = p["horizon_days"]
        target = p.get("target", "return")
        entry = {"family": p["family"], "expected_sign": p["expected_sign"], "horizon_days": h,
                 "registered_on": p["registered_on"], "target": target}
        if target == "market_flag":
            entry.update(market_flag_test(store, archive_root, gates))
            out["signals"][p["id"]] = entry
            continue
        key = (h, target)
        if key not in fwd_cache:
            fwd_cache[key] = forward_returns(archive_root, h)
            if target == "abs_return":
                fwd_cache[key] = fwd_cache[key].abs()
        s = sig[sig["signal_id"] == p["id"]] if len(sig) else sig
        for mode in ("live", "rehearsal"):
            part = s[s["live"] == (mode == "live")] if len(s) else s
            entry[mode] = summarize(ic_series(part, fwd_cache[key]) if len(part) else pd.Series(dtype=float),
                                    h, p["expected_sign"], gates)
        if p["id"] in LIVE_ONLY:
            entry["rehearsal"] = {"n_days": 0, "status": "live only: the model may know later events"}
        entry["companies_last_day"] = int(s[s["date"] == s["date"].max()]["ticker"].nunique()) if len(s) else 0
        out["signals"][p["id"]] = entry
    path = store.root / "lab" / "ic_provisional.json"
    write_json(path, out)
    return {"signals": {k: {"live_days": v["live"]["n_days"], "rehearsal_days": v["rehearsal"]["n_days"],
                            "rehearsal_t": v["rehearsal"].get("newey_west_t", v["rehearsal"].get("t"))} for k, v in out["signals"].items()}}
