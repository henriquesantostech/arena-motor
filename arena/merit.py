"""Merit statistics (rules/merit.json, design v2 §8.1-8.2): is a result skill or luck?

Pure functions on daily return arrays, plus `report(archive)` which computes them for every agent from the
journal and writes merit/report.json in the archive. Nothing here is stored in the journal, so it never
rewrites a past night.

  sharpe, moments           per-day Sharpe ratio, skewness, kurtosis (not excess)
  psr, expected_max_sr, dsr Probabilistic and Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014)
  effective_trials          N_eff = rho + (1 - rho) N from the mean pairwise correlation
  min_trl                   Minimum Track Record Length (Bailey & Lopez de Prado 2012)
  best_of_n                 agent vs the best of N monkeys, circular block bootstrap
  ols_hac                   OLS with Newey-West standard errors (alpha against factors)
  badge                     merit badge v2
"""
import hashlib
import json
import math
from statistics import NormalDist

import numpy as np

from . import config

RULES = json.loads((config.RULES_DIR / "merit.json").read_text(encoding="utf-8"))
DAYS_PER_YEAR = RULES["trading_days_per_year"]
EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def phi(x):
    return _N.cdf(x)


def phi_inv(p):
    return _N.inv_cdf(p)


# --- moments and Sharpe -------------------------------------------------------------------------------------
def sharpe(r):
    r = np.asarray(r, dtype=float)
    if len(r) < 2:
        return None
    s = r.std(ddof=1)
    return None if s == 0 else float(r.mean() / s)


def moments(r):
    """Sample skewness and kurtosis (not excess), population moments as in the DSR paper."""
    r = np.asarray(r, dtype=float)
    m = r.mean()
    s = r.std(ddof=0)
    if s == 0:
        return 0.0, 3.0
    z = (r - m) / s
    return float((z ** 3).mean()), float((z ** 4).mean())


# --- PSR / DSR ----------------------------------------------------------------------------------------------
def psr(sr, sr_star, t, skew=0.0, kurt=3.0):
    """Probability that the true Sharpe exceeds sr_star, given an estimate sr over t returns (per-period)."""
    den = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if t < 2 or den <= 0:
        return None
    return phi((sr - sr_star) * math.sqrt(t - 1) / math.sqrt(den))


def expected_max_sr(n_eff, var_sr):
    """Expected maximum per-period Sharpe of n_eff unskilled trials whose Sharpe estimates have variance var_sr."""
    if n_eff < 2 or var_sr <= 0:
        return 0.0
    return math.sqrt(var_sr) * ((1 - EULER_GAMMA) * phi_inv(1 - 1 / n_eff)
                                + EULER_GAMMA * phi_inv(1 - 1 / (n_eff * math.e)))


def dsr(sr, t, skew, kurt, n_eff, var_sr):
    return psr(sr, expected_max_sr(n_eff, var_sr), t, skew, kurt)


def effective_trials(series, min_overlap=20):
    """series: dict name -> {date: return}. Returns (N, mean pairwise correlation rho, N_eff)."""
    names = sorted(series)
    n = len(names)
    cors = []
    for i in range(n):
        a = series[names[i]]
        for k in range(i + 1, n):
            b = series[names[k]]
            common = sorted(set(a) & set(b))
            if len(common) < min_overlap:
                continue
            x = np.array([a[d] for d in common])
            y = np.array([b[d] for d in common])
            if x.std() == 0 or y.std() == 0:
                continue
            cors.append(float(np.corrcoef(x, y)[0, 1]))
    rho = max(0.0, float(np.mean(cors))) if cors else 0.0
    return n, rho, rho + (1 - rho) * n


# --- MinTRL -------------------------------------------------------------------------------------------------
def min_trl(sr, skew=0.0, kurt=3.0, sr_star=0.0, confidence=0.95):
    """Minimum number of observations for PSR(sr_star) >= confidence. None when sr <= sr_star."""
    if sr is None or sr <= sr_star:
        return None
    return 1 + (1 - skew * sr + (kurt - 1) / 4 * sr ** 2) * (phi_inv(confidence) / (sr - sr_star)) ** 2


# --- best of N monkeys with a circular block bootstrap ------------------------------------------------------
def info_ratio(active):
    """Annualised information ratio of an array of active returns (last axis = days)."""
    a = np.asarray(active, dtype=float)
    sd = a.std(axis=-1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ir = a.mean(axis=-1) / sd * math.sqrt(DAYS_PER_YEAR)
    return np.where(sd > 0, ir, 0.0)


def circular_block_indices(t, block, rng):
    n_blocks = -(-t // block)
    starts = rng.integers(0, t, size=n_blocks)
    idx = (starts[:, None] + np.arange(block)[None, :]) % t
    return idx.ravel()[:t]


def seeded_rng(text):
    return np.random.default_rng(int(hashlib.sha256(text.encode()).hexdigest()[:16], 16))


def best_of_n(agent, monkeys, index, block, n_boot=1000, rng=None):
    """agent: (T,) returns; monkeys: (N, T); index: (T,). Statistic: information ratio vs the index.

    Returns the observed statistics, the bootstrap distribution of the best monkey, its p95, the p-value
    (1 + #best >= agent) / (B + 1) and the agent's percentile within the distribution.
    """
    agent = np.asarray(agent, dtype=float)
    monkeys = np.asarray(monkeys, dtype=float)
    index = np.asarray(index, dtype=float)
    t = len(agent)
    rng = rng or np.random.default_rng(0)
    obs_agent = float(info_ratio(agent - index))
    obs_monkeys = info_ratio(monkeys - index[None, :])
    best = np.empty(n_boot)
    act_m = monkeys - index[None, :]
    for b in range(n_boot):
        idx = circular_block_indices(t, max(1, min(block, t)), rng)
        best[b] = info_ratio(act_m[:, idx]).max()
    p95 = float(np.quantile(best, 0.95))
    return {
        "agent_ir": round(obs_agent, 4),
        "best_monkey_ir": round(float(obs_monkeys.max()), 4),
        "best_of_n_p50": round(float(np.quantile(best, 0.5)), 4),
        "best_of_n_p95": round(p95, 4),
        "p_value": round(float((1 + (best >= obs_agent).sum()) / (n_boot + 1)), 4),
        "percentile": round(float((best < obs_agent).mean()), 4),
        "above_p95": bool(obs_agent > p95),
        "monkeys": int(monkeys.shape[0]), "days": int(t), "block": int(block), "resamples": int(n_boot),
    }


# --- OLS with Newey-West standard errors ------------------------------------------------------------------
def ols_hac(y, X, lag=5):
    """y: (T,), X: (T, k) WITHOUT constant. Returns coefficients (constant first), NW standard errors, t."""
    y = np.asarray(y, dtype=float)
    X = np.column_stack([np.ones(len(y)), np.asarray(X, dtype=float)])
    t, k = X.shape
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    u = y - X @ beta
    xu = X * u[:, None]
    s = xu.T @ xu
    for L in range(1, min(lag, t - 1) + 1):
        w = 1 - L / (lag + 1)
        g = xu[L:].T @ xu[:-L]
        s += w * (g + g.T)
    cov = xtx_inv @ s @ xtx_inv
    se = np.sqrt(np.diag(cov))
    with np.errstate(divide="ignore", invalid="ignore"):
        tstat = np.where(se > 0, beta / se, np.nan)
    return beta, se, tstat


# --- merit badge v2 -------------------------------------------------------------------------------------------
def badge(days, dsr_value, above_p95, vs_index, official=True):
    """Merit badge v2 (rules/merit.json badge_v2). Returns (label, list of unmet conditions)."""
    unmet = []
    if days < 252:
        unmet.append("12 months of life")
    if dsr_value is None or dsr_value < RULES["dsr"]["threshold"]:
        unmet.append("DSR >= 0.95")
    if not above_p95:
        unmet.append("above the best-of-monkeys p95")
    if vs_index is None or vs_index <= 0:
        unmet.append("beats the S&P 500 net of costs")
    if unmet:
        return "provisional", unmet
    return ("merit" if official else "rehearsal"), unmet


# --- report for every agent (archive merit/report.json) ----------------------------------------------------------
INDEX_NAME = "S&P 500 (EUR)"


def _adjusted_closes(archive, cutoff):
    p = archive.read("prices")
    p = p[p["fetched_at"] <= cutoff][["date", "ticker", "close", "fetched_at"]].copy()
    e = archive.read("events")
    for _, s in e[(e["type"] == "split") & (e["fetched_at"] <= cutoff)].iterrows():
        m = (p["ticker"] == s["ticker"]) & (p["date"] < s["date"]) & (p["fetched_at"] < s["date"])
        p.loc[m, "close"] = p.loc[m, "close"] / float(s["value"])
    return p.pivot(index="date", columns="ticker", values="close").sort_index()


def factor_returns(journals, closes):
    """MOM and LOWVOL per day: top third minus bottom third on the previous night's raw signal (rules/merit.json)."""
    days = sorted(journals)
    out = {}
    for prev, d in zip(days, days[1:]):
        sig = journals[prev]["signals"]
        if prev not in closes.index or d not in closes.index:
            continue
        r = closes.loc[d] / closes.loc[prev] - 1
        row = {}
        for f, key in (("MOM", "mom_12m"), ("LOWVOL", "low_risk")):
            vals = sorted((v["raw"][key], t) for t, v in sig.items()
                          if v["raw"].get(key) is not None and t in r.index and np.isfinite(r[t]))
            k = len(vals) // 3
            if k < 5:
                row = None
                break
            low = [t for _, t in vals[:k]]
            high = [t for _, t in vals[-k:]]
            row[f] = float(r[high].mean() - r[low].mean())
        if row:
            out[d] = row
    return out


def report(archive, n_boot=1000):
    from .evolution import evidence_label, value_history
    from .metrics import indicators
    days = archive.journal_days()
    if not days:
        return {"date": None}
    last = archive.read_journal(days[-1])
    journals = {d: {"signals": archive.read_journal(d)["signals"]} for d in days}
    history = value_history(archive, "9999-12-31")
    st = last["state"]
    everyone = {**{n: p for n, p in st["participants"].items() if p["type"] == "agent"}, **st.get("graveyard", {})}
    min_days = RULES["sharpe"]["min_days"]

    def returns(name, born):
        s = [(d, v[name]) for d, v in history.items() if d >= born and name in v]
        return s, {s[i][0]: s[i][1] / s[i - 1][1] - 1 for i in range(1, len(s))}

    idx_series, idx_ret = returns(INDEX_NAME, "")
    trials, srs = {}, []
    for n, p in everyone.items():
        _, r = returns(n, p["born"])
        if len(r) >= min_days:
            trials[n] = r
            sr = sharpe(list(r.values()))
            if sr is not None:
                srs.append(sr)
    n_trials, rho, n_eff = effective_trials(trials)
    var_sr = float(np.var(srs, ddof=1)) if len(srs) > 1 else 0.0
    sr_star = expected_max_sr(n_eff, var_sr)
    monkeys = None
    mpath = archive.root / "monkeys" / "values.csv"
    if mpath.exists():
        import pandas as pd
        monkeys = pd.read_csv(mpath, dtype={"date": str}).set_index("date")
    closes = _adjusted_closes(archive, last["inputs"]["cutoff"])
    factors = factor_returns(journals, closes)
    official = archive.cfg.get("mode") == "official" and not archive.cfg.get("rehearsal")
    agents = {}
    for n, p in sorted(st["participants"].items()):
        if p["type"] != "agent":
            continue
        series, r = returns(n, p["born"])
        ds = sorted(r)
        x = np.array([r[d] for d in ds])
        row = {"days": len(ds), "born": p["born"]}
        ind = indicators(n, series, idx_series, p, None, days[-1][:4]) if len(series) > 1 else None
        row["vs_index"] = ind["vs_index"] if ind else None
        if len(ds) >= min_days and sharpe(x) is not None:
            sr = sharpe(x)
            g3, g4 = moments(x)
            mt = min_trl(sr, g3, g4)
            row.update({
                "sharpe_annual": round(sr * math.sqrt(DAYS_PER_YEAR), 4), "skew": round(g3, 4), "kurtosis": round(g4, 4),
                "psr0": _r(psr(sr, 0.0, len(x), g3, g4)),
                "dsr": _r(psr(sr, sr_star, len(x), g3, g4)),
                "min_trl_days": None if mt is None else round(mt, 1),
                "min_trl_years": None if mt is None else round(mt / DAYS_PER_YEAR, 2),
            })
        else:
            row.update({"sharpe_annual": None, "psr0": None, "dsr": None, "min_trl_days": None, "min_trl_years": None})
        bon = None
        if monkeys is not None and len(ds) >= RULES["best_of_monkeys"]["min_days"]:
            common = [d for d in ds if d in monkeys.index and d in idx_ret]
            prev_ok = [d for d in common if monkeys.index.get_loc(d) > 0]
            if len(prev_ok) >= RULES["best_of_monkeys"]["min_days"]:
                mv = monkeys.to_numpy(dtype=float)
                pos = np.array([monkeys.index.get_loc(d) for d in prev_ok])
                mret = (mv[pos] / mv[pos - 1] - 1).T
                block = max(21, int(p["dna"].get("min_hold_days") or 0))
                bon = best_of_n(np.array([r[d] for d in prev_ok]), mret, np.array([idx_ret[d] for d in prev_ok]),
                                block, n_boot, seeded_rng(f"best-of-n|{n}|{days[-1]}"))
        row["best_of_monkeys"] = bon
        alpha = None
        fdays = [d for d in ds if d in factors and d in idx_ret]
        if len(fdays) >= RULES["alpha"]["min_days"]:
            y = np.array([r[d] for d in fdays])
            X = np.array([[idx_ret[d], factors[d]["MOM"], factors[d]["LOWVOL"]] for d in fdays])
            beta, se, t = ols_hac(y, X, lag=5)
            alpha = {"alpha_annual": round(float(beta[0]) * DAYS_PER_YEAR, 4), "t": _r(t[0]),
                     "beta_market": _r(beta[1]), "beta_momentum": _r(beta[2]), "beta_low_vol": _r(beta[3]),
                     "days": len(fdays)}
        row["alpha"] = alpha
        lab, unmet = badge(row["days"], row["dsr"], bool(bon and bon["above_p95"]), row["vs_index"], official)
        row["badge"] = lab
        row["badge_missing"] = unmet
        agents[n] = row
    return {
        "date": days[-1], "rules_version": RULES["version"], "evidence": evidence_label(archive.cfg),
        "trials": {"n": n_trials, "mean_correlation": round(rho, 4), "n_effective": round(n_eff, 2),
                   "sharpe_variance_per_day": round(var_sr, 8),
                   "expected_best_sharpe_annual": round(sr_star * math.sqrt(DAYS_PER_YEAR), 4)},
        "explain": ("With {n} agents tried so far, the best one would show an annual Sharpe of about {x} by luck alone."
                    .format(n=n_trials, x=round(sr_star * math.sqrt(DAYS_PER_YEAR), 2))),
        "agents": agents,
    }


def _r(x, k=4):
    return None if x is None or not np.isfinite(x) else round(float(x), k)


def run(archive, n_boot=1000):
    rep = report(archive, n_boot)
    path = archive.root / "merit" / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rep, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return rep
