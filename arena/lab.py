"""Signal Lab (design v2, section 8.3): shadow evaluation of every signal. It never touches money.

Inputs (contract in docs/contracts.md):
  * engine price signals, read from the journal (signal ids "price.<name>", z-scores, known at the night's cutoff);
  * external shadow signals, CSV files in the archive at intel/signals/shadow/YYYY/*.csv with columns
    date, ticker, signal_id, value, published_at, recorded_at (ISO 8601 UTC; larger value = more optimistic);
  * a pre-registration per signal: rules/signals/<signal_id>.json.

Point in time: a value enters day D only if published_at <= cutoff(D) and recorded_at <= cutoff(D),
where cutoff(D) is the cutoff stored in the journal of night D. If several rows exist for the same
(date, ticker, signal_id), the one recorded last before the cutoff wins.

Outputs (archive): lab/ic.csv (one row per signal and day) and lab/report.json (statistics and gates).
Everything is recomputed from the stored inputs, so the outputs are deterministic.
"""
import json
import math

import numpy as np
import pandas as pd

from . import config

SHADOW_COLUMNS = ["date", "ticker", "signal_id", "value", "published_at", "recorded_at"]
REGISTRATION_FIELDS = ["signal_id", "family", "hypothesis", "expected_sign", "horizon_days", "data",
                       "admission_test", "registered_on", "owner"]
REGISTRATION_DIR = config.RULES_DIR / "signals"
GATES = {
    "min_observations": 250,
    "min_nw_t": 3.0,
    "subperiods": 3,
    "min_same_sign_subperiods": 2,
    "min_residual_nw_t": 2.0,
    "decay_haircut": 0.5,
    "min_stocks_per_day": 20,
}
ROUND_TRIP = 2 * (config.FX_COST + config.SLIPPAGE)


# --- registrations --------------------------------------------------------------------
def registrations():
    out = {}
    for p in sorted(REGISTRATION_DIR.glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        out[r["signal_id"]] = r
    return out


def validate_registration(r):
    problems = [f"missing {f}" for f in REGISTRATION_FIELDS if f not in r]
    if r.get("expected_sign") not in (1, -1):
        problems.append("expected_sign must be 1 or -1")
    if not isinstance(r.get("horizon_days"), int) or not 1 <= r.get("horizon_days", 0) <= 126:
        problems.append("horizon_days must be an integer between 1 and 126")
    return problems


# --- inputs -------------------------------------------------------------------------------
def _ts(s):
    return str(s).replace("Z", "").replace("+00:00", "")[:19]


def load_signals(archive):
    """Long table date, ticker, signal_id, value with the point-in-time rule applied."""
    cutoffs, rows = {}, []
    for d in archive.journal_days():
        j = archive.read_journal(d)
        cutoffs[d] = _ts(j["inputs"]["cutoff"])
        for t, s in j["signals"].items():
            for name, v in s["z"].items():
                rows.append((d, t, f"price.{name}", float(v)))
    price = pd.DataFrame(rows, columns=["date", "ticker", "signal_id", "value"])
    files = sorted((archive.root / "intel" / "signals" / "shadow").glob("*/*.csv"))
    if not files:
        return price, cutoffs
    ext = pd.concat([pd.read_csv(f, dtype={"date": str, "ticker": str, "signal_id": str,
                                            "published_at": str, "recorded_at": str}) for f in files],
                    ignore_index=True)
    ext = ext[SHADOW_COLUMNS]
    ext = ext[ext["date"].isin(cutoffs)]
    cut = ext["date"].map(cutoffs)
    ok = (ext["published_at"].map(_ts) <= cut) & (ext["recorded_at"].map(_ts) <= cut)
    ext = ext[ok].copy()
    ext["_rec"] = ext["recorded_at"].map(_ts)
    ext = ext.sort_values(["date", "ticker", "signal_id", "_rec"], kind="mergesort")
    ext = ext.drop_duplicates(["date", "ticker", "signal_id"], keep="last")
    ext = ext[["date", "ticker", "signal_id", "value"]].astype({"value": float})
    return pd.concat([price, ext], ignore_index=True), cutoffs


def adjusted_opens(archive):
    """Days × companies opening prices, adjusted for splits (same rule as View.adjusted_close)."""
    p = archive.read("prices")[["date", "ticker", "open", "fetched_at"]].copy()
    ev = archive.read("events")
    for _, s in ev[ev["type"] == "split"].iterrows():
        m = (p["ticker"] == s["ticker"]) & (p["date"] < s["date"]) & (p["fetched_at"] < s["date"])
        p.loc[m, "open"] = p.loc[m, "open"] / float(s["value"])
    days = sorted(p.loc[p["ticker"] == config.INDEX_PRICE, "date"].unique())
    tab = p.pivot(index="date", columns="ticker", values="open").reindex(days)
    return tab


# --- statistics ---------------------------------------------------------------------------
def _rank_ic(a, b):
    ra, rb = a.rank(), b.rank()
    if ra.std(ddof=0) == 0 or rb.std(ddof=0) == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def newey_west_t(x, lag):
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 3:
        return None
    m = x.mean()
    e = x - m
    var = e @ e / n
    for k in range(1, min(lag, n - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k] / n)
    if var <= 0:
        return None
    return float(m / math.sqrt(var / n))


def _residual(values, controls):
    X = np.column_stack([np.ones(len(values))] + controls)
    beta, *_ = np.linalg.lstsq(X, values, rcond=None)
    return values - X @ beta


# --- the lab ---------------------------------------------------------------------------------
def run(archive):
    regs = registrations()
    signals, cutoffs = load_signals(archive)
    opens = adjusted_opens(archive)
    days = list(opens.index)
    pos = {d: i for i, d in enumerate(days)}
    sector = {c["ticker"]: c["sector"] for c in config.UNIVERSE["companies"]}
    controls_src = signals[signals["signal_id"].isin(["price.mom_12m", "price.low_risk"])]
    controls = {k: g.pivot(index="ticker", columns="signal_id", values="value")
                for k, g in controls_src.groupby("date")}
    ic_rows, report = [], {}
    for sid, g in signals.groupby("signal_id"):
        reg = regs.get(sid)
        if reg is None or validate_registration(reg):
            report[sid] = {"status": "rejected", "why": "no valid pre-registration in rules/signals/"}
            continue
        h, sign = reg["horizon_days"], reg["expected_sign"]
        first_obs = g["date"].min()
        series, resid, spreads, costs, prev_top = [], [], [], [], {}
        for d, gd in g.groupby("date"):
            i = pos.get(d)
            if i is None or i + 1 + h >= len(days):
                continue
            fwd = opens.iloc[i + 1 + h] / opens.iloc[i + 1] - 1
            s = gd.set_index("ticker")["value"]
            both = pd.concat([s, fwd], axis=1, keys=["s", "r"]).dropna()
            if len(both) < GATES["min_stocks_per_day"]:
                continue
            ic = _rank_ic(both["s"], both["r"])
            if ic is None:
                continue
            ic *= sign
            row = {"date": d, "signal_id": sid, "horizon_days": h, "n": int(len(both)), "ic": round(ic, 6)}
            # residual IC after momentum, low volatility and sector
            c = controls.get(d)
            if c is not None and not sid.startswith(("price.mom_12m", "price.low_risk")):
                cc = both.join(c, how="inner").dropna()
                if len(cc) >= GATES["min_stocks_per_day"]:
                    dummies = pd.get_dummies(cc.index.map(sector)).astype(float).values[:, 1:]
                    res = _residual(cc["s"].values, [cc[k].values for k in c.columns] + [dummies])
                    ric = _rank_ic(pd.Series(res, index=cc.index), cc["r"])
                    if ric is not None:
                        row["residual_ic"] = round(ric * sign, 6)
                        resid.append(ric * sign)
            # top tercile: gross spread over the universe, and turnover cost
            k = max(1, len(both) // 3)
            top = set((both["s"] * sign).sort_values(ascending=False, kind="mergesort").index[:k])
            spreads.append(float(both.loc[list(top), "r"].mean() - both["r"].mean()))
            back = days[i - h] if i - h >= 0 else None
            if back in prev_top:
                costs.append(len(top - prev_top[back]) / k * ROUND_TRIP)
            prev_top[d] = top
            series.append(ic)
            ic_rows.append(row)
        n = len(series)
        t = newey_west_t(series, h) if n else None
        rt = newey_west_t(resid, h) if resid else None
        sub = [float(np.mean(c)) for c in np.array_split(np.array(series), GATES["subperiods"]) if len(c)] if n >= GATES["subperiods"] else []
        same = sum(1 for x in sub if x > 0)
        alpha = GATES["decay_haircut"] * (float(np.mean(spreads)) if spreads else 0.0)
        cost = float(np.mean(costs)) if costs else None
        gates = {
            "pre_registered": reg["registered_on"] <= first_obs,
            "observations": n >= GATES["min_observations"],
            "ic_positive_nw_t": t is not None and t > GATES["min_nw_t"],
            "subperiod_sign": same >= GATES["min_same_sign_subperiods"],
            "adds_value_after_controls": sid.startswith(("price.mom_12m", "price.low_risk")) or (rt is not None and rt > GATES["min_residual_nw_t"]),
            "alpha_beats_costs": cost is not None and alpha > cost,
        }
        report[sid] = {
            "status": "passes_gates" if all(gates.values()) else "shadow",
            "family": reg["family"], "horizon_days": h, "expected_sign": sign,
            "observations": n, "first_observation": first_obs,
            "mean_ic": None if not n else round(float(np.mean(series)), 6),
            "nw_t": None if t is None else round(t, 3),
            "subperiod_mean_ic": [round(x, 6) for x in sub],
            "mean_residual_ic": None if not resid else round(float(np.mean(resid)), 6),
            "residual_nw_t": None if rt is None else round(rt, 3),
            "haircut_alpha_per_horizon": round(alpha, 6),
            "turnover_cost_per_horizon": None if cost is None else round(cost, 6),
            "gates": gates,
        }
    for sid, reg in regs.items():   # registered but no usable observation yet
        if sid not in report:
            report[sid] = {"status": "shadow", "family": reg.get("family"), "observations": 0,
                           "note": "registered; no point-in-time observation yet"}
    ic = pd.DataFrame(ic_rows, columns=["date", "signal_id", "horizon_days", "n", "ic", "residual_ic"])
    ic = ic.sort_values(["signal_id", "date"], kind="mergesort")
    out = archive.root / "lab"
    out.mkdir(parents=True, exist_ok=True)
    ic.to_csv(out / "ic.csv", index=False, lineterminator="\n")
    summary = {"gates": GATES, "round_trip_cost": ROUND_TRIP,
               "note": "Shadow only. Passing the gates does not change any DNA; admission is a logged rule change.",
               "signals": dict(sorted(report.items()))}
    (out / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, allow_nan=False) + "\n",
                                     encoding="utf-8", newline="\n")
    return summary
