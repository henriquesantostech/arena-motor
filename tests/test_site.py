"""The website build: data/arena.json has everything the page and the cards need; data/days/ one shard per night."""
import json

from arena.night import process
from arena.site import build

from test_engine import make_archive


def _data(root):
    return json.loads((root / "site" / "data" / "arena.json").read_text(encoding="utf-8"))


def test_site_builds_with_everything(tmp_path):
    arch, days = make_archive(tmp_path / "a")
    process(arch)
    build(arch)
    out = tmp_path / "a" / "site"
    for f in ("index.html", "_headers", "favicon.svg", "data/arena.json"):
        assert (out / f).exists(), f
    assert any((out / "assets").glob("*.js")), "built app"
    shards = sorted((out / "data" / "days").glob("*.json"))
    assert [s.stem for s in shards] == arch.journal_days()
    sh = json.loads(shards[-1].read_text(encoding="utf-8"))
    assert sh["date"] == shards[-1].stem and len(sh["values"]) == 32 and "inputs" in sh and "positions" in sh
    d = _data(tmp_path / "a")
    kinds = [p["type"] for p in d["p"]]
    assert kinds.count("agent") == 20 and kinds.count("monkey") == 10
    assert kinds.count("index") == 1 and kinds.count("equal") == 1
    assert len(d["species"]) == 5 and all(p["sp"] in d["species"] for p in d["p"] if p["type"] == "agent")
    assert len({p["id"] for p in d["p"]}) == 32
    n = len(d["meta"]["dates"])
    assert n >= 2 and len(d["band"]) == n
    for p in d["p"]:
        assert len(p["s"]) == n and p["value"] == p["s"][-1]
        assert abs(sum(h["eur"] for h in p["hold"]) + p["cash"] - p["value"]) < 1.0, p["name"]
    agent = next(p for p in d["p"] if p["type"] == "agent")
    assert agent["dna"] and sum(agent["dna"]["w"].values()) == 100


def test_site_before_first_night(tmp_path):
    arch, days = make_archive(tmp_path / "a")
    build(arch)   # no journal yet: the page must still open
    d = _data(tmp_path / "a")
    assert d["p"] == [] and d["meta"]["updated"] is None


def test_site_uses_the_offline_monkeys(tmp_path):
    arch, days = make_archive(tmp_path / "a")
    process(arch)
    jd = arch.journal_days()
    (tmp_path / "a" / "monkeys").mkdir()
    summary = {"date": jd[-1], "monkeys": 1000, "return_p05": -0.03, "return_median": 0.0, "return_p95": 0.04, "best_of_n": 0.09,
               "luck_band": {"dates": jd, "p05": [-0.01] * len(jd), "p95": [0.02] * len(jd)},
               "agents": {"Arrow-01": {"return": 0.01, "percentile_vs_all_monkeys": 0.61, "percentile_vs_mirroring_monkeys": 0.55}}}
    (tmp_path / "a" / "monkeys" / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    build(arch)
    d = _data(tmp_path / "a")
    assert d["luck"]["n"] == 1000 and d["luck"]["p95"] == 0.04 and len(d["luck"]["s"]) == len(d["meta"]["dates"])
    a = next(p for p in d["p"] if p["name"] == "Arrow-01")
    assert a["pctAll"] == 0.61 and a["pctMirror"] == 0.55
    (tmp_path / "a" / "monkeys" / "summary.json").write_text("{broken", encoding="utf-8")
    build(arch)   # a broken file never breaks the site
    assert _data(tmp_path / "a")["luck"] is None
