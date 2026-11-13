"""Engine tests on made-up data (no internet needed).

Run:  .venv\\Scripts\\python.exe -m pytest -q
"""
import numpy as np
import pandas as pd
import pytest

from arena import config, sources
from arena.archive import Archive
from arena.market import apply_events, buy, new_participant, sell
from arena.night import process, replay

FETCHED = "2026-01-01T00:00:00"


def make_archive(root, n_days=300, day_zero_idx=270, tweak=None):
    """Fake archive: random walk for the 101 companies and the indices."""
    rng = np.random.default_rng(42)
    days = pd.bdate_range("2025-01-02", periods=n_days).strftime("%Y-%m-%d").tolist()
    rows = []
    for t in config.universe_tickers() + config.INDICES:
        base = 7000.0 if t.startswith("^") else rng.uniform(20, 400)
        rets = rng.normal(0.0004, 0.015, n_days)
        closes = base * np.cumprod(1 + rets)
        opens = closes * (1 + rng.normal(0, 0.003, n_days))
        for d, o, c in zip(days, opens, closes):
            rows.append({"date": d, "ticker": t, "open": round(o, 4), "high": round(max(o, c), 4),
                         "low": round(min(o, c), 4), "close": round(c, 4), "volume": 1000})
    prices = pd.DataFrame(rows)
    events = pd.DataFrame(columns=["date", "ticker", "type", "value"])
    if tweak:
        prices, events = tweak(prices, events, days)
    fx = pd.DataFrame({"date": days, "eurusd": [1.10] * n_days})
    archive = Archive(root)
    archive.write_cfg({"name": "test", "mode": "trial", "day_zero": days[day_zero_idx], "universe_frozen_on": "x"})
    archive.append("prices", prices, FETCHED)
    archive.append("events", events, FETCHED)
    archive.append("fx", fx, FETCHED)
    return archive, days


# --- the referee's arithmetic --------------------------------------------------------
def participant():
    return new_participant({"name": "X", "type": "agent", "species": "t", "dna": None}, "2026-01-02")


def test_buy_with_costs():
    p = participant()
    r = buy(p, "AAA", 10000.0, 100.0, 1.10, "2026-01-02")
    # €10,000 - 0.15% = €9,985 -> $10,983.50 ; price with slippage $100.05
    assert r["shares"] == pytest.approx(109.780109, abs=1e-6)
    assert p["cash"] == 90000.0
    assert r["fx_cost_eur"] == 15.0
    assert r["slippage_cost_eur"] == pytest.approx(109.780109 * 0.05 / 1.10, abs=0.01)


def test_sell_with_costs_and_gain():
    p = participant()
    buy(p, "AAA", 10000.0, 100.0, 1.10, "2026-01-02")
    shares = p["positions"]["AAA"]["shares"]
    r = sell(p, "AAA", shares, 110.0, 1.10, "2026-02-02")
    expected = round(shares * 110.0 * 0.9995 / 1.10 * 0.9985, 2)
    assert r["eur"] == expected
    assert r["gain_eur"] == round(expected - 10000.0, 2)
    assert "AAA" not in p["positions"]
    assert p["totals"]["closed"] == 1 and p["totals"]["winners"] == 1
    assert p["totals"]["realized_gains"]["2026"] == r["gain_eur"]


def test_dividend_withholding_and_split():
    p = participant()
    buy(p, "AAA", 10000.0, 100.0, 1.10, "2026-01-02")
    shares = p["positions"]["AAA"]["shares"]
    cash = p["cash"]
    ev = pd.DataFrame([{"ticker": "AAA", "type": "dividend", "value": 1.0},
                       {"ticker": "BBB", "type": "dividend", "value": 5.0}])
    done = apply_events(p, ev, 1.10)
    assert len(done) == 1
    assert p["cash"] == round(cash + round(shares * 1.0 * 0.85 / 1.10 * 0.9985, 2), 2)
    apply_events(p, pd.DataFrame([{"ticker": "AAA", "type": "split", "value": 4.0}]), 1.10)
    assert p["positions"]["AAA"]["shares"] == pytest.approx(shares * 4, abs=1e-6)
    assert p["positions"]["AAA"]["cost_eur"] == 10000.0


# --- the whole night -----------------------------------------------------------------
def test_nights_replay_identically(tmp_path):
    archive, days = make_archive(tmp_path / "a")
    done = process(archive)
    assert done[0] == days[270] and done[-1] == days[-1]
    for d in (done[0], done[5], done[-1]):
        r = replay(archive, d)
        assert r["identical"], r
    j = archive.read_journal(done[-1])
    assert set(j["values"]) == {p["name"] for p in config.POPULATION["participants"]}
    for name, p in j["state"]["participants"].items():
        assert p["cash"] >= 0, name


def test_cannot_see_the_future(tmp_path):
    """Changing prices after D must not change anything about night D."""
    a1, days = make_archive(tmp_path / "a")
    process(a1, until=days[280])
    j1 = a1.read_journal(days[280])

    def change_future(prices, events, days_):
        m = prices["date"] > days_[280]
        prices.loc[m, "close"] = prices.loc[m, "close"] * 3
        prices.loc[m, "open"] = prices.loc[m, "open"] * 0.2
        return prices, events

    a2, _ = make_archive(tmp_path / "b", tweak=change_future)
    process(a2, until=days[280])
    j2 = a2.read_journal(days[280])
    for k in ("values", "signals", "decisions", "state"):
        assert j1[k] == j2[k], k


def test_late_data_does_not_change_a_finished_night(tmp_path):
    """A row that reaches the archive after the night ran is not used when that night is replayed."""
    archive, days = make_archive(tmp_path / "a")
    process(archive, until=days[275])
    late = pd.DataFrame([{"date": days[275], "ticker": "ZZZ", "open": 1.0, "high": 1.0,
                          "low": 1.0, "close": 1.0, "volume": 1}])
    archive.append("prices", late, "2027-01-01T00:00:00")
    assert replay(archive, days[275])["identical"]


def test_delisting_forces_a_sale(tmp_path):
    def drop_aapl(prices, events, days_):
        return prices[~((prices["ticker"] == "AAPL") & (prices["date"] > days_[272]))], events

    archive, days = make_archive(tmp_path / "a", tweak=drop_aapl)
    process(archive)
    j = archive.read_journal(days[-1])
    assert "AAPL" in j["state"]["delisted"]
    ew = j["state"]["participants"]["Equal weight"]
    assert "AAPL" not in ew["positions"]
    out = archive.read_journal(j["state"]["delisted"]["AAPL"])
    sales = [e for e in out["decisions"]["Equal weight"]["fills"] if e["ticker"] == "AAPL"]
    assert sales and sales[0]["reason"]["cause"] == "delisting"


def test_split_does_not_look_like_a_crash(tmp_path):
    """A split stored after the old prices: signals adjust and the check does not exclude the company."""
    def split(prices, events, days_):
        d = days_[285]
        m = (prices["ticker"] == "MSFT") & (prices["date"] >= d)
        for c in ("open", "high", "low", "close"):
            prices.loc[m, c] = (prices.loc[m, c] / 4).round(4)
        events = pd.DataFrame([{"date": d, "ticker": "MSFT", "type": "split", "value": 4.0}])
        return prices, events

    archive, days = make_archive(tmp_path / "a", tweak=split)
    # as in real life: the old rows were fetched before the split
    p = archive.read("prices").copy()
    p.loc[p["date"] >= days[285], "fetched_at"] = days[285] + "T23:00:00"
    p.to_csv(archive.path("prices"), index=False, lineterminator="\n")
    e = archive.read("events").copy()
    e["fetched_at"] = days[285] + "T23:00:00"
    e.to_csv(archive.path("events"), index=False, lineterminator="\n")
    archive._cache.clear()
    process(archive)
    j = archive.read_journal(days[285])
    assert "MSFT" not in j["checks"]["excluded"]
    assert abs(j["signals"]["MSFT"]["raw"]["mom_1m"]) < 0.5
    before = archive.read_journal(days[284])["state"]["participants"]["Equal weight"]["positions"]["MSFT"]["shares"]
    after = j["state"]["participants"]["Equal weight"]["positions"]["MSFT"]["shares"]
    assert after == pytest.approx(before * 4, abs=1e-5)
    v = [archive.read_journal(d)["values"]["Equal weight"] for d in (days[284], days[285])]
    assert abs(v[1] / v[0] - 1) < 0.05


def test_independent_audit(tmp_path):
    from arena.audit import audit
    archive, days = make_archive(tmp_path / "a")
    process(archive)
    for name in ("Arrow-01", "Wave-03", "Monkey-02", "Equal weight", "S&P 500 (EUR)"):
        assert "matches" in audit(archive, name, tmp_path / f"{name}.csv")


def test_source_registry():
    """Every role the engine needs has a registered adapter with terms and licence recorded."""
    reg = {s["id"]: s for s in sources.registry()}
    for role in ("daily_prices", "fx_rates", "price_crosscheck"):
        mod = sources._primary(role)
        assert reg[mod.SOURCE_ID]["terms"] and reg[mod.SOURCE_ID]["license"] and reg[mod.SOURCE_ID]["use"]
    assert all(s.get("redistribution") for s in reg.values())
