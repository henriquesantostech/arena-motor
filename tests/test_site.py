"""The website build: data.js has everything the one-look page and the cards need."""
import json

from arena.night import process
from arena.site import build

from test_engine import make_archive


def _data(root):
    text = (root / "site" / "data.js").read_text(encoding="utf-8")
    assert text.startswith("window.ARENA=")
    return json.loads(text[len("window.ARENA="):].rstrip().rstrip(";"))


def test_site_builds_with_everything(tmp_path):
    arch, days = make_archive(tmp_path / "a")
    process(arch)
    build(arch)
    out = tmp_path / "a" / "site"
    for f in ("index.html", "app.js", "arena3d.js", "style.css", "_headers", "data.js"):
        assert (out / f).exists(), f
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
