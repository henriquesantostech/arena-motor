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
    pages = sorted((out / "data" / "journal").glob("*.json"))
    assert [x.stem for x in pages] == arch.journal_days()
    pg = json.loads(pages[-1].read_text(encoding="utf-8"))
    assert {"front", "markets", "companies", "arena", "world", "people", "sources"} <= set(pg)
    assert pg["sources"]["journal"]["sha256"] and pg["world"] is None
    corp = json.loads((out / "data" / "corpus.json").read_text(encoding="utf-8"))["passages"]
    ids = [c["id"] for c in corp]
    assert len(ids) == len(set(ids)) and "about" in ids and any(c["k"] == "decision" for c in corp)
    assert all(c["d"] is None or c["d"] <= d["meta"]["updated"] for c in corp)
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


def test_readings_fingerprint_and_recomputed_decisions(tmp_path):
    """What the Verify button does in the browser: the readings hash matches, and every agent decision
    recomputed from that night's readings gives the stored score and rank."""
    import hashlib
    from arena.site import readings_text
    arch, days = make_archive(tmp_path / "a")
    process(arch)
    build(arch)
    root = tmp_path / "a" / "site" / "data"
    d = json.loads((root / "arena.json").read_text(encoding="utf-8"))
    checked = 0
    for p in d["p"]:
        if p["type"] != "agent":
            continue
        for l in p["log"]:
            r = l.get("r") or {}
            if r.get("score") is None or not l.get("dd"):
                continue
            sh = json.loads((root / "days" / f"{l['dd']}.json").read_text(encoding="utf-8"))
            sig = sh["sig"]
            assert hashlib.sha256(readings_text(sig["cols"], sig["z"]).encode()).hexdigest() == sig["sha256"]
            skip = set(sh["excluded"]) | set(sh["delisted"])
            sc = {t: round(sum(v * p["dna"]["w"].get(c, 0) / 100 for v, c in zip(z, sig["cols"])), 4)
                  for t, z in sig["z"].items() if t not in skip}
            ranking = sorted(sc, key=lambda t: (-sc[t], t))
            assert abs(sc[l["t"]] - r["score"]) <= 1.5e-4
            assert ranking.index(l["t"]) + 1 == r["rank"]
            checked += 1
    assert checked > 0
