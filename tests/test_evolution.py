"""Evolution on made-up data: DNA operations, selection, and the monthly evaluation inside the night."""
import json

import numpy as np
import pytest

from arena import config, evolution
from arena.night import process, replay

from test_engine import make_archive

FOUNDERS = [p for p in config.POPULATION["participants"] if p["type"] == "agent"]


def test_weights_add_up_to_100_with_largest_remainder():
    raw = {s: 0 for s in config.SIGNALS}
    raw.update({"mom_1m": 1, "mom_3m": 1, "mom_6m": 1})
    w = evolution.to_hundred(raw)
    assert sum(w.values()) == 100
    assert (w["mom_1m"], w["mom_3m"], w["mom_6m"]) == (34, 33, 33)   # tie -> signal order
    assert evolution.to_hundred({s: 0 for s in config.SIGNALS}) is None


def test_children_stay_inside_the_rules():
    rng = evolution.rng_for("test")
    for k in range(300):
        a, b = FOUNDERS[k % 20]["dna"], FOUNDERS[(k * 7 + 3) % 20]["dna"]
        c = evolution.crossover_and_mutate(a, b, rng)
        assert sum(c["weights"].values()) == 100
        assert all(c["weights"][s] == 0 for s in config.SIGNALS if s not in evolution.ADMITTED)
        assert all(v >= 0 for v in c["weights"].values())
        for g in evolution.MANAGEMENT:
            if g != "max_weight":
                assert c[g] in evolution.GRIDS[g], (g, c[g])
        assert c["max_weight"] * c["n_holdings"] >= 0.999 and c["max_weight"] <= 0.2
        im = evolution.immigrant_dna(rng)
        assert sum(im["weights"].values()) == 100 and im["max_weight"] * im["n_holdings"] >= 0.999


def test_child_genes_come_from_the_parents_before_mutation():
    # with identical parents, every weight is within 5 points before rescaling and genes move one step at most
    a = FOUNDERS[0]["dna"]
    rng = evolution.rng_for("same")
    for _ in range(200):
        c = evolution.crossover_and_mutate(a, a, rng)
        for g in ("n_holdings", "review_days", "min_hold_days", "rank_band"):
            assert abs(evolution.GRIDS[g].index(c[g]) - evolution.GRIDS[g].index(a[g])) <= 1


def test_founders_are_closest_to_their_own_species():
    hits = sum(evolution.nearest_species(p["dna"]["weights"]) == p["species"] for p in FOUNDERS)
    assert hits >= 16   # species overlap a little (e.g. a contrarian with a 12-month trend weight)


def _members():
    return {p["name"]: {"name": p["name"], "type": "agent", "species": p["species"], "dna": p["dna"]} for p in FOUNDERS}


def test_selection_kills_the_worst_four_and_breeds_from_the_best_five():
    members = _members()
    ranking = [{"name": p["name"], "fitness": float(i), "vs_index": 0.0} for i, p in enumerate(FOUNDERS)]
    dead, births = evolution.select_and_breed(ranking, members, list(members), 1, "evolution|2027-06-01")
    assert dead == [FOUNDERS[i]["name"] for i in (0, 1, 2, 3)]   # lowest fitness first
    best5 = {FOUNDERS[i]["name"] for i in range(15, 20)}
    assert len(births) == 4 and [b["immigrant"] for b in births] == [False, False, False, True]
    for b in births[:3]:
        assert set(b["parents"]) <= best5 and len(set(b["parents"])) == 2
        assert b["generation"] == 2 and b["cohort"] == 1
    assert births[3]["parents"] is None and births[3]["generation"] == 1
    assert [b["slot"] for b in births] == [0, 1, 2, 3]
    assert len({b["name"] for b in births}) == 4 and not ({b["name"] for b in births} & set(members))
    # same day, same draws
    again = evolution.select_and_breed(ranking, members, list(members), 1, "evolution|2027-06-01")
    assert again == (dead, births)


def test_selection_keeps_at_least_five_eligible_and_ranks_missing_scores_last():
    members = _members()
    names = [p["name"] for p in FOUNDERS[:7]]
    ranking = [{"name": n, "fitness": 1.0, "vs_index": 0.0} for n in names]
    ranking[3]["fitness"] = None
    dead, births = evolution.select_and_breed(ranking, members, list(members), 2, "x")
    assert len(dead) == 2 and dead[0] == names[3] and len(births) == 2
    assert all(not b["immigrant"] for b in births)
    assert evolution.select_and_breed(ranking[:5], members, list(members), 2, "x") == ([], [])


def test_eligibility_counts_calendar_months_from_the_first_trading_day():
    days = ["2027-02-26", "2027-03-01", "2027-03-02", "2027-05-03", "2027-06-01"]
    assert not evolution.is_eligible("2027-02-26", "2027-05-03", days)   # life starts 1 March: 2 months
    assert evolution.is_eligible("2027-02-26", "2027-06-01", days)
    assert evolution.is_first_trading_day_of_month("2027-06-01", days)
    assert not evolution.is_first_trading_day_of_month("2027-03-02", days)


@pytest.fixture(scope="module")
def evolved(tmp_path_factory):
    """130 made-up nights with evolution switched on from the start (shared by the tests below)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(evolution.RULES, "effective_from", "2000-01-01")
        archive, days = make_archive(tmp_path_factory.mktemp("evolved"), n_days=400, day_zero_idx=270)
        done = process(archive)
        yield archive, done


def test_monthly_evolution_in_the_night_replays_identically(evolved):
    archive, done = evolved
    evaluations = [d for d in done if "evolution" in archive.read_journal(d)]
    assert len(evaluations) >= 3
    first = archive.read_journal(evaluations[0])["evolution"]
    assert len(first["ranking"]) == 20 and len(first["deaths"]) == 4 and len(first["births"]) == 4
    last = archive.read_journal(done[-1])
    state = last["state"]
    agents = [p for p in state["participants"].values() if p["type"] == "agent"]
    assert len(agents) == 20
    assert len(state["graveyard"]) == 4 * len(evaluations) - sum(
        4 - len(archive.read_journal(d)["evolution"]["deaths"]) for d in evaluations)
    assert sorted(evolution.identity(p)["slot"] for p in agents) == list(range(20))
    # the dead are never deleted: their record keeps the portfolio and the reason
    for name, g in state["graveyard"].items():
        assert g["death"]["died"] in evaluations and g["pending"] == [] and name not in state["participants"]
    # newborns start with fresh capital and trade from the next open
    born = archive.read_journal(evaluations[0])["evolution"]["births"][0]["name"]
    j0 = archive.read_journal(evaluations[0])
    assert j0["values"][born] == config.CAPITAL and j0["state"]["participants"][born]["pending"]
    j1 = archive.read_journal(done[done.index(evaluations[0]) + 1])
    assert j1["decisions"][born]["fills"]
    # monkeys and benchmarks never die
    assert all(n in state["participants"] for n in ("Monkey-01", "S&P 500 (EUR)", "Equal weight"))
    # an evaluation night and the night after replay identically
    for d in (evaluations[0], done[done.index(evaluations[0]) + 1], evaluations[-1]):
        assert replay(archive, d)["identical"], d


def test_nothing_changes_before_the_effective_date(tmp_path):
    archive, days = make_archive(tmp_path, n_days=285, day_zero_idx=270)
    done = process(archive)
    assert all("evolution" not in archive.read_journal(d) for d in done)
    assert "graveyard" not in archive.read_journal(done[-1])["state"]


def test_offline_monkeys_null_evolution_and_merit_reports(evolved):
    from arena import merit, monkeys
    archive, done = evolved
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(evolution.RULES, "effective_from", "2000-01-01")
        m = monkeys.run(archive, n=60)
        last = archive.read_journal(done[-1])
        alive = sorted(n for n, p in last["state"]["participants"].items() if p["type"] == "agent")
        assert sorted(m["agents"]) == alive          # monkeys follow the seats, newborns included
        # the monkeys mirroring a seat with a newborn start again with fresh capital on its birth night
        import pandas as pd
        vals = pd.read_csv(archive.root / "monkeys" / "values.csv", dtype={"date": str}).set_index("date")
        first_eval = next(d for d in done if "evolution" in archive.read_journal(d))
        slot = archive.read_journal(first_eval)["evolution"]["births"][0]["slot"]
        cols = [c for i, c in enumerate(vals.columns) if i % 20 == slot]
        assert (vals.loc[first_eval, cols] == config.CAPITAL).all()
        other = [c for i, c in enumerate(vals.columns) if i % 20 not in
                 {b["slot"] for b in archive.read_journal(first_eval)["evolution"]["births"]}]
        assert (vals.loc[first_eval, other] != config.CAPITAL).any()
        assert monkeys.run(archive, n=60)["replay_identical"]
        r = evolution.run(archive, worlds=2)
        assert r["evaluations"] >= 3 and r["agents_ever"] == 20 + len(last["state"]["graveyard"])
        null = json.loads((archive.root / "evolution" / "null.json").read_text(encoding="utf-8"))
        for w in null["worlds"]:
            assert len(w["evaluations"]) == r["evaluations"]
            assert sum(1 for x in w["members"].values() if x["died"] is None) == 20
        assert len(null["comparison"]) == r["evaluations"]
        assert evolution.run(archive, worlds=2)["replay_identical"]   # second run gives the same ghosts
        t = json.loads((archive.root / "evolution" / "tree.json").read_text(encoding="utf-8"))
        names = {x["name"] for x in t["nodes"]}
        assert all(set(x["parents"] or []) <= names for x in t["nodes"])
        assert "never evidence" in t["evidence"]
        rep = merit.run(archive, n_boot=100)
        assert rep["trials"]["n"] >= 20 and sorted(rep["agents"]) == alive
        old = [a for a in rep["agents"].values() if a["days"] >= 60]
        assert old and all(a["dsr"] is not None and a["alpha"] and a["best_of_monkeys"] for a in old)
        assert all(a["badge"] == "provisional" for a in rep["agents"].values())   # nobody has 12 months


def test_label_uses_badge_v2_from_the_merit_report():
    from arena.metrics import label
    ind = {"days": 300, "vs_index": 0.1, "score": 2.0}
    assert label(ind, [0.0] * 100) == "provisional"
    assert label(ind, [0.0] * 100, {"badge": "merit"}) == "merit"
    assert label(ind, [0.0] * 100, {"badge": "rehearsal"}) == "provisional"
