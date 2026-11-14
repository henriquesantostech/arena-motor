"""Wikidata (CC0), snapshotted daily: who the universe companies are (QID, English Wikipedia article, CEO,
chairperson, country, industry) and who governs where (heads of state and government, central bank heads).

PIT: Wikidata is edited continuously and its history is not a clean "as known at" record, so the only honest
timestamp is our own snapshot time: published_at = recorded_at = when we queried. A fact that disappears from
a later snapshot is closed with an op='end' row (never deleted). Wikidata is crowd-edited and can be wrong;
facts carry confidence 0.8 and the CEO edge is cross-checked against SEC filings when they disagree.
"""
import re

from .. import http
from ..entities import base_name, company_id, norm
from ..wkb import facts_as_of, fact

SOURCE_ID = "wikidata"
VERSION = "1"
SPARQL = "https://query.wikidata.org/sparql"
COUNTRIES = {"Q30": "US", "Q148": "CN", "Q183": "DE", "Q142": "FR", "Q145": "GB", "Q17": "JP", "Q159": "RU",
             "Q212": "UA", "Q801": "IL", "Q668": "IN", "Q865": "TW", "Q794": "IR", "Q851": "SA", "Q16": "CA",
             "Q96": "MX", "Q155": "BR", "Q884": "KR", "Q38": "IT", "Q29": "ES", "Q45": "PT", "Q43": "TR",
             "Q55": "NL", "Q39": "CH", "Q408": "AU", "Q1028": "MA", "Q79": "EG", "Q252": "ID", "Q881": "VN"}
INSTITUTIONS = {"Q53536": "org:FED", "Q8901": "org:ECB", "Q14915": "org:BOJ", "Q1052127": "org:PBOC",
                "Q190538": "org:BOE"}

Q_COMPANIES = """
SELECT ?item ?itemLabel ?ticker ?cik ?article ?ceo ?ceoLabel ?chair ?chairLabel ?country ?industryLabel WHERE {
  VALUES ?ticker { %s }
  ?item p:P414 ?st . ?st pq:P249 ?ticker .
  OPTIONAL { ?item wdt:P5531 ?cik }
  OPTIONAL { ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> }
  OPTIONAL { ?item p:P169 ?cs . ?cs ps:P169 ?ceo . FILTER NOT EXISTS { ?cs pq:P582 ?e1 } }
  OPTIONAL { ?item p:P488 ?hs . ?hs ps:P488 ?chair . FILTER NOT EXISTS { ?hs pq:P582 ?e2 } }
  OPTIONAL { ?item wdt:P17 ?country }
  OPTIONAL { ?item wdt:P452 ?industry }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}"""

Q_LEADERS = """
SELECT ?org ?role ?person ?personLabel ?start WHERE {
  VALUES ?org { %s }
  VALUES ?prop { p:P35 p:P6 p:P488 }
  ?org ?prop ?s . ?s ?ps ?person .
  ?propEntity wikibase:claim ?prop ; wikibase:statementProperty ?ps .
  FILTER NOT EXISTS { ?s pq:P582 ?end }
  OPTIONAL { ?s pq:P580 ?start }
  BIND(STRAFTER(STR(?prop), "http://www.wikidata.org/prop/") AS ?role)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}"""
ROLE = {"P35": "head_of_state", "P6": "head_of_government", "P488": "chairperson"}


def _query(ctx, q):
    r, sha, _ = http.fetch(ctx.store, SOURCE_ID, SPARQL, params={"query": q, "format": "json"},
                           headers={"Accept": "application/sparql-results+json"}, timeout=90)
    rows = [{k: v["value"] for k, v in b.items()} for b in r.json()["results"]["bindings"]]
    return rows, sha


def _s(x):
    """DuckDB/pandas give NaN for empty text; treat it as None."""
    return None if x is None or (isinstance(x, float) and x != x) else x


def _qid(uri):
    return uri.rsplit("/", 1)[-1] if uri else None


def _best(cands, name, cik):
    """Picks the Wikidata item for one ticker: SEC CIK match first, then name similarity."""
    want = set(norm(base_name(name)).split())

    def score(c):
        lab = set(norm(base_name(c.get("itemLabel", ""))).split())
        return ((cik is not None and c.get("cik") == cik), len(want & lab) / max(1, len(want | lab)), "article" in c)
    return max(cands, key=score)


def ingest(ctx):
    store = ctx.store
    tickers = [c["ticker"] for c in http.universe()]
    cik_map = (store.state("sec_cik_map") or {}).get("map", {})
    rows, sha = _query(ctx, Q_COMPANIES % " ".join(f'"{t}"' for t in tickers))
    by_t = {}
    for r in rows:
        by_t.setdefault(r["ticker"], []).append(r)
    new_facts, ents = [], []
    for c in http.universe():
        t = c["ticker"]
        if t not in by_t:
            continue
        best = _best(by_t[t], c["name"], cik_map.get(t))
        q = _qid(best["item"])
        same = [r for r in by_t[t] if r["item"] == best["item"]]
        article = best.get("article", "")
        title = re.sub(r"^https://en\.wikipedia\.org/wiki/", "", article)
        ents.append({"entity_id": company_id(t), "kind": "company", "name": c["name"], "ticker": t,
                     "cik": cik_map.get(t) or best.get("cik"), "qid": q,
                     "aliases": sorted({c["name"], base_name(c["name"]), best.get("itemLabel", "")} - {""}),
                     "recorded_at": ctx.now, "source_id": SOURCE_ID, "source_hash": sha})
        if title:
            new_facts.append(("co", company_id(t), "enwiki_title", None, title))
        for r in same:
            if r.get("ceo"):
                new_facts.append(("co", company_id(t), "ceo", f"wd:{_qid(r['ceo'])}", r.get("ceoLabel")))
            if r.get("chair"):
                new_facts.append(("co", company_id(t), "chairperson", f"wd:{_qid(r['chair'])}", r.get("chairLabel")))
            if r.get("country"):
                cc = COUNTRIES.get(_qid(r["country"]))
                new_facts.append(("co", company_id(t), "country", f"country:{cc}" if cc else f"wd:{_qid(r['country'])}", None))
            if r.get("industryLabel"):
                new_facts.append(("co", company_id(t), "industry", None, r["industryLabel"]))
    orgs = {**{q: f"country:{cc}" for q, cc in COUNTRIES.items()}, **INSTITUTIONS}
    lrows, lsha = _query(ctx, Q_LEADERS % " ".join(f"wd:{q}" for q in orgs))
    for r in lrows:
        role = ROLE.get(r.get("role"))
        org = orgs.get(_qid(r.get("org")))
        if role and org:
            new_facts.append(("leader", org, role, f"wd:{_qid(r['person'])}", r.get("personLabel")))
            ents.append({"entity_id": f"wd:{_qid(r['person'])}", "kind": "person", "name": r.get("personLabel"),
                         "ticker": None, "cik": None, "qid": _qid(r["person"]), "aliases": [r.get("personLabel")],
                         "recorded_at": ctx.now, "source_id": SOURCE_ID, "source_hash": lsha})
    store.add("entities", ents)
    # Diff against what the knowledge base currently holds from Wikidata: assert new, end vanished.
    con = store.connect()
    current = facts_as_of(con, ctx.now, mode="strict")
    current = current[current["source_id"] == SOURCE_ID] if len(current) else current
    def key(subj, pred, obj, val):
        obj, val = _s(obj), _s(val)
        return (subj, pred, obj) if obj else (subj, pred, val or "")
    have = {}
    for r in (current.itertuples() if len(current) else []):
        have[key(r.subject_id, r.predicate, r.object_id, r.value)] = r
    snap = {}
    for kind, subj, pred, obj, val in new_facts:
        snap.setdefault(key(subj, pred, obj, val), (kind, subj, pred, obj, val))
    out = []
    for k in sorted(set(snap) - set(have)):
        kind, subj, pred, obj, val = snap[k]
        out.append(fact(subj, pred, object_id=obj, value=val, valid_from=ctx.now, published_at=ctx.now,
                        source_id=SOURCE_ID, source_hash=sha if kind == "co" else lsha, extractor="wikidata.sparql",
                        extractor_version=VERSION, confidence=0.8, recorded_at=ctx.now))
    for k in sorted(set(have) - set(snap)):
        r = have[k]
        out.append(fact(r.subject_id, r.predicate, object_id=_s(r.object_id), value=_s(r.value), valid_from=r.valid_from,
                        valid_to=ctx.now, published_at=ctx.now, source_id=SOURCE_ID, source_hash=sha,
                        extractor="wikidata.sparql", extractor_version=VERSION, confidence=0.8, op="end",
                        recorded_at=ctx.now))
    store.add("facts", out)
    return {"companies": len(by_t), "facts_changed": len(out)}
