"""Offline tests for the phase 2 intelligence layer (no network)."""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("duckdb", reason="phase 2 tests need requirements-intel.txt")

from arena.intel import wkb
from arena.intel.entities import Linker
from arena.intel.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path, run_id="t1")


def _ctx(store, now="2026-11-14T06:00:00Z"):
    return SimpleNamespace(store=store, now=now, backfill_from=None, linker=Linker(), out_of_time=lambda: False)


def test_raw_archive_is_content_addressed_and_immutable(store):
    sha1, p1 = store.put_raw("src", "https://x/a.json", b'{"a":1}', "application/json", day="2026-11-14")
    sha2, p2 = store.put_raw("src", "https://x/a.json", b'{"a":1}', "application/json", day="2026-11-14")
    assert sha1 == sha2 and p1 == p2
    assert store.get_raw(p1) == b'{"a":1}'


def test_partitions_never_overwrite(store):
    store.add("signals", [{"date": "2026-11-13", "ticker": "AAPL", "signal_id": "s", "value": 1.0,
                           "published_at": "x", "recorded_at": "y"}])
    store.flush("2026-11-14")
    store.add("signals", [{"date": "2026-11-13", "ticker": "MSFT", "signal_id": "s", "value": 2.0,
                           "published_at": "x", "recorded_at": "y"}])
    store.flush("2026-11-14")
    files = list((store.root / "tables" / "signals").glob("*/*.parquet"))
    assert len(files) == 2
    assert len(store.read("signals")) == 2


def test_bitemporal_facts_as_of(store):
    f = lambda **k: wkb.fact("co:AAPL", "ceo", source_id="t", source_hash="h", extractor="t", extractor_version="1", **k)
    store.add("facts", [f(object_id="wd:Q1", value="Old CEO", valid_from="2020-01-01T00:00:00Z",
                          published_at="2020-01-01T00:00:00Z", recorded_at="2026-11-01T00:00:00Z")])
    store.add("facts", [f(object_id="wd:Q1", value="Old CEO", valid_from="2020-01-01T00:00:00Z", valid_to="2026-11-10T00:00:00Z",
                          published_at="2026-11-10T00:00:00Z", recorded_at="2026-11-10T00:00:00Z", op="end"),
                        f(object_id="wd:Q2", value="New CEO", valid_from="2026-11-10T00:00:00Z",
                          published_at="2026-11-10T00:00:00Z", recorded_at="2026-11-10T00:00:00Z")])
    store.flush()
    con = store.connect()
    before = wkb.facts_as_of(con, "2026-11-05T00:00:00Z", predicate="ceo")
    after = wkb.facts_as_of(con, "2026-11-12T00:00:00Z", predicate="ceo")
    assert before["object_id"].tolist() == ["wd:Q1"]
    assert after["object_id"].tolist() == ["wd:Q2"]
    # strict mode hides what we had not recorded yet, rehearsal mode trusts the publication time
    early = wkb.facts_as_of(con, "2025-01-01T00:00:00Z", predicate="ceo", mode="strict")
    rehearsal = wkb.facts_as_of(con, "2025-01-01T00:00:00Z", predicate="ceo", mode="rehearsal")
    assert early.empty and rehearsal["object_id"].tolist() == ["wd:Q1"]


def test_revisions_are_new_rows_dated_when_seen(store):
    from arena.intel.sources.common import add_observations
    ctx = _ctx(store, "2026-11-14T06:00:00Z")
    add_observations(ctx, [{"series_id": "x", "entity_id": "country:US", "obs_date": "2026-11-12", "value": 1.0,
                            "published_at": "2026-11-12T23:00:00Z"}], "t", "h1")
    store.flush()
    ctx2 = _ctx(store, "2026-11-15T06:00:00Z")
    n_same = add_observations(ctx2, [{"series_id": "x", "entity_id": "country:US", "obs_date": "2026-11-12",
                                      "value": 1.0, "published_at": "2026-11-12T23:00:00Z"}], "t", "h2")
    n_rev = add_observations(ctx2, [{"series_id": "x", "entity_id": "country:US", "obs_date": "2026-11-12",
                                     "value": 1.5, "published_at": "2026-11-12T23:00:00Z"}], "t", "h2")
    store.flush()
    assert n_same == 0 and n_rev == 1
    con = store.connect()
    v1 = wkb.observations_as_of(con, "2026-11-14T12:00:00Z", "x")
    v2 = wkb.observations_as_of(con, "2026-11-16T00:00:00Z", "x")
    assert v1["value"].tolist() == [1.0] and v2["value"].tolist() == [1.5]


def test_edgar_dissemination_rule():
    from arena.intel.sources.edgar import accepted_utc, disseminated_utc
    assert accepted_utc("2026-11-12T23:58:20.000Z") == "2026-11-12T23:58:20Z"
    assert disseminated_utc("2026-11-12T23:58:20Z", "4") == "2026-11-12T23:58:20Z"     # 18:58 NY < 22:00
    assert disseminated_utc("2026-11-12T23:00:00Z", "8-K") == "2026-11-13T11:00:00Z"   # 18:00 NY > 17:30
    assert disseminated_utc("2026-11-13T23:00:00Z", "10-Q") == "2026-11-16T11:00:00Z"  # Friday late -> Monday


def test_decision_cutoff_is_end_of_new_york_day():
    assert wkb.decision_cutoff("2026-11-13") == "2026-11-14T04:59:59Z"
    assert wkb.decision_cutoff("2026-07-01") == "2026-07-02T03:59:59Z"


def test_house_ptr_parser():
    from arena.intel.sources.house_ptr import parse_ptr
    text = ("SP Apple Inc. - Common Stock (AAPL) [ST]\nP 10/01/202610/20/2026$1,001 -\n$15,000\n"
            "Microsoft Corporation (MSFT) [ST] S (partial) 09/15/2026 10/02/2026 $15,001 - $50,000\n"
            "Treasury Bill (6-Week) [GS] P 10/20/202610/20/2026$15,001 - $50,000")
    tx = parse_ptr(text)
    assert [(t["ticker"], t["action"], t["size_low"], t["size_high"]) for t in tx] == [
        ("AAPL", "buy", 1001.0, 15000.0), ("MSFT", "sell", 15001.0, 50000.0)]
    assert tx[0]["traded_on"] == "2026-10-01" and tx[1]["partial"]


def test_ttm_and_growth():
    from arena.intel.shadow import _growth, _ytd_ttm
    rows = pd.DataFrame([
        {"dur": "12m", "obs_date": "2025-12-31", "value": 100.0},
        {"dur": "9m", "obs_date": "2025-09-30", "value": 70.0},
        {"dur": "9m", "obs_date": "2026-09-30", "value": 90.0},
        {"dur": "3m", "obs_date": "2026-09-30", "value": 32.0},
        {"dur": "3m", "obs_date": "2025-09-30", "value": 25.0},
    ])
    assert _ytd_ttm(rows, "2026-11-13") == pytest.approx(120.0)
    assert _growth(rows[rows["dur"] == "3m"]) == pytest.approx(0.28)


def test_newey_west_and_ic():
    from arena.intel.lab import ic_series, newey_west_t
    rng = np.random.default_rng(0)
    assert newey_west_t(rng.normal(0, 1, 500), 5) == pytest.approx(0, abs=3)
    assert newey_west_t(rng.normal(0.5, 1, 500), 5) > 5
    days = ["2026-01-02", "2026-01-05"]
    tick = [f"T{i}" for i in range(30)]
    sig = pd.DataFrame([{"date": d, "ticker": t, "value": float(i)} for d in days for i, t in enumerate(tick)])
    fwd = pd.DataFrame([[i / 100 for i in range(30)]] * 2, index=days, columns=tick)
    ics = ic_series(sig, fwd)
    assert ics.round(6).tolist() == [1.0, 1.0]


def test_linker_is_deterministic():
    lk = Linker()
    assert lk.link_text("Bank of America and $NVDA rally; Apple Inc. (NASDAQ: AAPL) flat") == ["co:AAPL", "co:BAC", "co:NVDA"]
    assert lk.link_span("V") is None           # ambiguous ticker words are not linked
    assert lk.link_span("JPMorgan") == "co:JPM"


def test_exam_scoring():
    from arena.intel.readers.exam import load, score_llm
    items, meta = load()
    assert len(items) == 40 and meta["frozen_on"] == "2026-11-14"
    perfect = [{"doc_id": it["id"], "output": {"event_type": it["gold"]["event_type"], "companies": [
        {"ticker": t, "direction": it["gold"]["direction"] or 0, "magnitude": 1, "horizon": "days"}
        for t in it["gold"]["tickers"]]}} for it in items]
    s = score_llm(items, perfect)
    assert s["json_valid"] == 1.0 and s["event_type_accuracy"] == 1.0 and s["ticker_f1"] == 1.0
    assert s["direction_accuracy"] == 1.0


def test_registry_entries_are_complete():
    from arena.intel.sources import registry
    need = {"id", "provider", "adapter", "data", "pit_field", "rate_limit", "terms", "terms_url", "license", "use",
            "redistribution", "terms_checked_on", "enabled"}
    for s in registry():
        assert need <= set(s), s["id"]
        if not s["enabled"]:
            assert s.get("excluded_reason"), s["id"]


def test_shadow_signals_are_preregistered():
    from arena.intel.shadow import preregistered
    ids = {p["id"] for p in preregistered()}
    for p in preregistered():
        assert p["expected_sign"] in (-1, 1) and p["horizon_days"] > 0 and p["registered_on"]
    assert {"intel.insider_cluster_buy_90d", "intel.attention_spike_3d", "intel.earnings_yield_ttm"} <= ids


def test_signal_dated_d_uses_previous_session_information():
    days = ["2026-11-12", "2026-11-13"]
    assert wkb.info_cutoff("2026-11-13", days) == wkb.decision_cutoff("2026-11-12")
    assert wkb.signal_days(days, "2026-11-14T06:00:00Z")[-1] == "2026-11-16"   # Friday -> Monday session
    assert wkb.signal_days(days, "2026-11-14T03:00:00Z")[-1] == "2026-11-13"   # Friday's cutoff not passed yet


def test_edgar_header_and_index_parsing():
    from arena.intel.sources.edgar import accepted_utc, parse_header, parse_master_index
    h = parse_header("<SEC-HEADER>x\n<ACCEPTANCE-DATETIME>20261112085241\n<ACCESSION-NUMBER>0001045810-26-000082\n"
                     "<TYPE>8-K\n<ITEMS>5.02\n<ITEMS>9.01\n<FILING-DATE>20261112\n")
    assert h["items"] == ["5.02", "9.01"] and h["type"] == "8-K"
    assert accepted_utc(h["accepted"]) == "2026-11-12T13:52:41Z"     # header clock is New York
    idx = "CIK|Company Name|Form Type|Date Filed|File Name\n---\n1045810|NVIDIA CORP|8-K|20261112|edgar/data/1045810/0001045810-26-000082.txt\n1000275|ROYAL BANK|424B2|20261112|x.txt\n"
    assert parse_master_index(idx, {"0001045810"}) == [("0001045810", "NVIDIA CORP", "8-K", "edgar/data/1045810/0001045810-26-000082.txt")]


def test_store_add_accepts_dataframes(store):
    assert store.add("signals", pd.DataFrame(columns=["date"])) == 0
    df = pd.DataFrame([{"date": "2026-11-13", "ticker": "AAPL", "signal_id": "intel.x", "value": 1.0,
                        "published_at": "a", "recorded_at": "b"}])
    assert store.add("signals", df) == 1


def test_brief_salvage_keeps_whole_sectors():
    from arena.intel.readers.brief import SECTORS, _salvage
    s0, s1 = SECTORS[0], SECTORS[1]
    raw = ('{"headline": "H", "sectors": [{"sector": "%s", "score": -2, "reason": "r", "citations": ["a"]}, '
           '{"sector": "%s", "score": 1, "reason": "cut' % (s0, s1))
    out = _salvage(raw)
    assert out["partial"] and out["headline"] == "H"
    assert [(x["sector"], x["score"]) for x in out["sectors"]] == [(s0, -2)]
    assert _salvage('{"head')["partial"]


def test_rehearsal_uses_only_readers_without_future_knowledge():
    from arena.intel.shadow import compute_day
    rd = pd.DataFrame([
        {"reader": "finbert", "score": 0.5, "output": None, "entity_ids": '["co:AAPL"]',
         "doc_published": "2026-01-05T15:00:00Z", "usable_at": "2026-11-16T00:00:00Z"},
        {"reader": "llm", "score": None, "output": '{"companies": [{"ticker": "AAPL", "direction": 1, "magnitude": 2}]}',
         "entity_ids": '["co:AAPL"]', "doc_published": "2026-01-05T15:00:00Z", "usable_at": "2026-11-16T00:00:00Z"}])
    empty = pd.DataFrame(columns=["subject_id", "predicate", "object_id", "value", "valid_from", "published_at",
                                  "recorded_at", "person_id", "ticker", "action", "note", "disclosed_at",
                                  "entity_id", "obs_date"])
    inp = SimpleNamespace(alerts=empty, facts=empty, views=empty, xbrl=empty, readings=rd, close=pd.DataFrame())
    cut = "2026-01-07T04:59:59Z"
    reh = {r["signal_id"] for r in compute_day(inp, "2026-01-06", ["AAPL"], cut, rehearsal=True)}
    live = {r["signal_id"] for r in compute_day(inp, "2026-01-06", ["AAPL"], cut)}
    assert reh == {"intel.news_sentiment_3d"}
    assert live == set()   # recorded after the cutoff: not usable live


def test_country_aliases():
    from arena.intel.site_export import _country_code
    assert _country_code("America") == "US" and _country_code("China") == "CN" and _country_code("Narnia") is None
