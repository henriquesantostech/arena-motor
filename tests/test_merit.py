"""Merit statistics on made-up data, checked against published reference values where they exist."""
import math

import numpy as np
import pytest

from arena import merit
from arena.lab import newey_west_t


def test_dsr_matches_the_published_example():
    # Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio", numerical example:
    # 100 trials, variance of annualised Sharpe 0.5, best annualised Sharpe 2.5, 5 years of daily data
    # (250 days a year, T = 1250), skewness -3, kurtosis 10 -> SR* = 0.1132 per day, DSR = 0.9004.
    per_year = 250
    var_sr = 0.5 / per_year
    sr_star = merit.expected_max_sr(100, var_sr)
    assert sr_star == pytest.approx(0.1132, abs=5e-5)
    d = merit.dsr(2.5 / math.sqrt(per_year), 1250, -3, 10, 100, var_sr)
    assert d == pytest.approx(0.9004, abs=5e-4)


def test_psr_without_trials_and_with_normal_returns():
    # No deflation: SR* = 0; normal returns (skew 0, kurt 3): PSR = Phi(SR sqrt(T-1) / sqrt(1 + SR^2/2))
    sr, t = 0.08, 500
    expected = merit.phi(sr * math.sqrt(t - 1) / math.sqrt(1 + sr ** 2 / 2))
    assert merit.dsr(sr, t, 0.0, 3.0, 1, 0.01) == pytest.approx(expected, abs=1e-12)
    assert merit.psr(0.0, 0.0, 100) == pytest.approx(0.5)


def test_expected_max_sharpe_agrees_with_simulation():
    rng = np.random.default_rng(1)
    n, sd = 50, 0.03
    sim = rng.normal(0, sd, size=(20000, n)).max(axis=1).mean()
    assert merit.expected_max_sr(n, sd ** 2) == pytest.approx(sim, rel=0.03)
    assert merit.expected_max_sr(1, sd ** 2) == 0.0


def test_min_trl_matches_the_design_figures_and_is_consistent_with_psr():
    # Design v2 §8.1: about 2.7 years for an annual Sharpe of 1.0 and about 11 years for 0.5 (normal returns)
    sr1 = 1.0 / math.sqrt(252)
    assert merit.min_trl(sr1) / 252 == pytest.approx(2.7, abs=0.05)
    assert merit.min_trl(0.5 / math.sqrt(252)) / 252 == pytest.approx(10.8, abs=0.1)
    # at exactly MinTRL observations, PSR(0) = 95%
    for sr, g3, g4 in [(0.1, 0.0, 3.0), (0.05, -1.2, 7.5), (0.2, 0.5, 4.0)]:
        n = merit.min_trl(sr, g3, g4)
        assert merit.psr(sr, 0.0, n, g3, g4) == pytest.approx(0.95, abs=1e-9)
    assert merit.min_trl(-0.01) is None and merit.min_trl(0.0) is None


def test_moments_of_a_known_sample():
    r = np.array([1.0, 2.0, 3.0, 4.0, 10.0])
    m, s = r.mean(), r.std()
    skew, kurt = merit.moments(r)
    assert skew == pytest.approx((((r - m) / s) ** 3).mean())
    assert kurt == pytest.approx((((r - m) / s) ** 4).mean())
    assert merit.sharpe([0.01, 0.01]) is None
    assert merit.sharpe([0.01, 0.03]) == pytest.approx(0.02 / np.std([0.01, 0.03], ddof=1))


def test_effective_trials_from_correlations():
    rng = np.random.default_rng(3)
    days = [f"d{i:03d}" for i in range(200)]
    base = rng.normal(0, 0.01, 200)
    same = {f"a{k}": dict(zip(days, base)) for k in range(5)}
    n, rho, n_eff = merit.effective_trials(same)
    assert (n, round(rho, 9), round(n_eff, 9)) == (5, 1.0, 1.0)
    indep = {f"a{k}": dict(zip(days, rng.normal(0, 0.01, 200))) for k in range(10)}
    n, rho, n_eff = merit.effective_trials(indep)
    assert n == 10 and rho < 0.05 and n_eff > 9.5
    # pairs with too little overlap are ignored
    short = {"x": dict(zip(days[:10], base[:10])), "y": dict(zip(days[:10], base[:10]))}
    assert merit.effective_trials(short)[1] == 0.0


def test_constant_only_regression_equals_the_lab_newey_west_t():
    rng = np.random.default_rng(5)
    x = rng.normal(0.001, 0.01, 300) + 0.3 * np.roll(rng.normal(0, 0.01, 300), 1)
    beta, se, t = merit.ols_hac(x, np.empty((300, 0)), lag=5)
    assert t[0] == pytest.approx(newey_west_t(x, 5), rel=1e-12)


def test_ols_hac_with_lag_zero_is_white_and_recovers_known_coefficients():
    rng = np.random.default_rng(7)
    T = 2000
    X = rng.normal(0, 0.01, size=(T, 3))
    y = 0.0004 + X @ np.array([0.9, 0.3, -0.2]) + rng.normal(0, 0.005, T)
    beta, se, t = merit.ols_hac(y, X, lag=0)
    Xc = np.column_stack([np.ones(T), X])
    u = y - Xc @ beta
    inv = np.linalg.inv(Xc.T @ Xc)
    white = np.sqrt(np.diag(inv @ (Xc.T * u ** 2) @ Xc @ inv))
    assert np.allclose(se, white, rtol=1e-10)
    assert beta[1:] == pytest.approx([0.9, 0.3, -0.2], abs=0.03)
    assert beta[0] == pytest.approx(0.0004, abs=0.00015)


def test_block_bootstrap_indices():
    rng = np.random.default_rng(0)
    idx = merit.circular_block_indices(100, 21, rng)
    assert len(idx) == 100 and idx.min() >= 0 and idx.max() < 100
    steps = np.diff(idx)
    # inside a block the days are consecutive (wrapping around the end)
    assert ((steps == 1) | (steps == -99)).sum() >= 100 - 5 - 1


def test_best_of_n_separates_skill_from_luck():
    rng = np.random.default_rng(11)
    T, N = 252, 300
    index = rng.normal(0.0003, 0.01, T)
    monkeys = index[None, :] + rng.normal(0, 0.004, size=(N, T))
    lucky = monkeys[np.argmax(merit.info_ratio(monkeys - index))]
    skilled = index + 0.003 + rng.normal(0, 0.004, T)   # information ratio about 12
    plain = index + rng.normal(0, 0.004, T)
    r_sk = merit.best_of_n(skilled, monkeys, index, 21, 300, np.random.default_rng(1))
    r_pl = merit.best_of_n(plain, monkeys, index, 21, 300, np.random.default_rng(1))
    r_lu = merit.best_of_n(lucky, monkeys, index, 21, 300, np.random.default_rng(1))
    assert r_sk["above_p95"] and r_sk["p_value"] < 0.01
    assert not r_pl["above_p95"] and r_pl["p_value"] > 0.5
    # even the luckiest monkey is not above the p95 of the best of its peers
    assert not r_lu["above_p95"]
    # the best of N under the null sits around sqrt(2 ln N) annualised-IR standard errors
    assert 2.0 < r_pl["best_of_n_p50"] < 5.0


def test_badge_v2():
    assert merit.badge(300, 0.97, True, 0.05) == ("merit", [])
    assert merit.badge(300, 0.97, True, 0.05, official=False) == ("rehearsal", [])
    label, unmet = merit.badge(200, 0.5, False, -0.01)
    assert label == "provisional" and len(unmet) == 4
    assert merit.badge(300, None, True, 0.05)[1] == ["DSR >= 0.95"]
