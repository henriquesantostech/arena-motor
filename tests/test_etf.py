"""ETF League tests on made-up prices (no internet needed)."""
import json

import numpy as np
import pandas as pd
import pytest

from arena import etf
from arena.archive import Archive


def make(tmp_path, n=700, seed=3, tweak_from=None):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2023-01-02", periods=n).strftime("%Y-%m-%d").tolist()
    rows = []
    for t in etf.TICKERS:
        c = 50 * np.cumprod(1 + rng.normal(0.0003, 0.01, n))
        if tweak_from is not None:
            c[tweak_from:] *= 3.0   # a different future
        o = c * (1 + rng.normal(0, 0.002, n))
        for d, oo, cc in zip(days, o, c):
            rows.append({"date": d, "ticker": t, "open": round(oo, 4), "high": cc, "low": cc, "close": round(cc, 4),
                         "volume": 1, "fetched_at": "2026-01-01T00:00:00"})
    root = tmp_path / "arc" / "etf" / "raw"
    root.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(root / "prices.csv", index=False)
    (root.parent / "league.json").write_text(json.dumps({"day_zero": days[500]}))
    return Archive(tmp_path / "arc"), days


@pytest.fixture(autouse=True)
def small(monkeypatch):
    monkeypatch.setitem(etf.RULES, "monkeys", 20)
    monkeypatch.setitem(etf.RULES, "rehearsal_start", "2023-12-01")


def test_universe_is_frozen_and_complete():
    assert len(etf.STRATEGIES) == 10 and len(etf.REFS) == 2
    assert etf.CASH == "XEON.DE" and len(etf.TICKERS) == len(set(etf.TICKERS))
    ids = {s["id"] for s in etf.SIGNALS["signals"]}
    assert ids == {"etf.mom_12_1", "etf.mom_6m", "etf.trend_10m", "etf.low_vol_12m", "etf.short_reversal"}


def test_run_report_and_determinism(tmp_path):
    a, days = make(tmp_path)
    r1 = etf.run(a, fetch_data=False)
    assert r1["status"] == "ok" and r1["live_days"] == len(days) - 1 - 500
    rep = json.loads((tmp_path / "arc" / "etf" / "report.json").read_text())
    assert rep["live"]["monkeys"]["n"] == 20 and rep["rehearsal"]["label"].startswith("technical rehearsal")
    assert set(rep["live"]["participants"]) == set(etf.REFS + etf.STRATEGIES)
    world = rep["live"]["participants"]["ref.world_hold"]
    assert world["costs"] > 0 and world["tax"] == 0.0   # bought once, never sold
    assert rep["verdict"]["months_live"] < 12 and set(rep["verdict"]["per_strategy"].values()) <= {"too early", "failed (drawdown)"}
    first = (tmp_path / "arc" / "etf" / "report.json").read_text()
    etf.run(a, fetch_data=False)
    assert (tmp_path / "arc" / "etf" / "report.json").read_text() == first


def test_no_look_ahead(tmp_path):
    """Changing prices after day D cannot change what happened up to D (decisions use only the past)."""
    a1, days = make(tmp_path / "x")
    a2, _ = make(tmp_path / "y", tweak_from=650)
    etf.run(a1, fetch_data=False)
    etf.run(a2, fetch_data=False)
    v1 = pd.read_csv(tmp_path / "x" / "arc" / "etf" / "values.csv", index_col=0)
    v2 = pd.read_csv(tmp_path / "y" / "arc" / "etf" / "values.csv", index_col=0)
    upto = v1.index[v1.index < days[649]]
    pd.testing.assert_frame_equal(v1.loc[upto], v2.loc[upto])


def test_tax_on_realised_gain_only(tmp_path):
    a, days = make(tmp_path)
    dates, cl, op, valid = etf.matrices(etf._a(a))
    etf._DATES = dates
    w = np.zeros(etf.K)
    w[etf.IDX["EUNL.DE"]] = 1.0
    cash = np.zeros(etf.K)
    cash[etf.IDX[etf.CASH]] = 1.0
    cl2 = cl.copy()
    cl2[301:, etf.IDX["EUNL.DE"]] *= 2   # the ETF doubles, then we sell into cash
    op2 = op.copy()
    op2[301:, etf.IDX["EUNL.DE"]] *= 2
    vals, info = etf.run_portfolio(op2, cl2, {299: w, 400: cash}, 299, 450)
    gain = sum(info["realised_gains"].values())
    assert gain > 0 and info["tax"] == pytest.approx(0.28 * gain, abs=0.05)
    assert info["costs"] > 0
