"""Small, site-friendly JSON files exported from the knowledge base (private archive, login-only site).

  intel/site/docs.json    {doc_id: {title, url, source, kind, published_at}} for every document cited by a brief
                          in the last 90 days plus the notable documents of the last 14 days
  intel/site/world.json   {as_of, countries: {ISO2: {name, lat, lon, events, conflict_share, goldstein, tone, day,
                          head_of_state, head_of_government}}, rates, fx, risk, events: [{title, day, topic, doc_id}]}
  intel/site/graph.json   {as_of, nodes: [{id, type, label, sector?}], edges: [{a, b, kind, since, value?}]}
All values are as known at the export time (strict mode). Raw source text never leaves the archive.
"""
import json
from datetime import date, timedelta

from .. import config
from ..archive import write_json
from .store import utcnow
from .wkb import documents_as_of, facts_as_of, observations_as_of

COUNTRY = {  # ISO2: (name, lat, lon) — approximate centroids for the globe
    "US": ("United States", 39.8, -98.6), "CN": ("China", 35.9, 104.2), "RU": ("Russia", 61.5, 105.3),
    "UA": ("Ukraine", 48.4, 31.2), "IL": ("Israel", 31.0, 34.9), "IR": ("Iran", 32.4, 53.7),
    "TW": ("Taiwan", 23.7, 121.0), "IN": ("India", 20.6, 79.0), "JP": ("Japan", 36.2, 138.3),
    "DE": ("Germany", 51.2, 10.5), "FR": ("France", 46.2, 2.2), "GB": ("United Kingdom", 55.4, -3.4),
    "KR": ("South Korea", 35.9, 127.8), "KP": ("North Korea", 40.3, 127.5), "SA": ("Saudi Arabia", 23.9, 45.1),
    "TR": ("Turkey", 39.0, 35.2), "MX": ("Mexico", 23.6, -102.6), "CA": ("Canada", 56.1, -106.3),
    "BR": ("Brazil", -14.2, -51.9), "EG": ("Egypt", 26.8, 30.8), "SY": ("Syria", 34.8, 39.0),
    "VE": ("Venezuela", 6.4, -66.6), "PK": ("Pakistan", 30.4, 69.3), "IQ": ("Iraq", 33.2, 43.7),
    "YE": ("Yemen", 15.6, 48.5), "LB": ("Lebanon", 33.9, 35.9), "IT": ("Italy", 41.9, 12.6),
    "ES": ("Spain", 40.5, -3.7), "PT": ("Portugal", 39.4, -8.2), "NL": ("Netherlands", 52.1, 5.3),
    "CH": ("Switzerland", 46.8, 8.2), "AU": ("Australia", -25.3, 133.8), "ID": ("Indonesia", -0.8, 113.9),
    "VN": ("Vietnam", 14.1, 108.3), "MA": ("Morocco", 31.8, -7.1),
}
NOTABLE = ("filing:8-K", "fedreg:presidential_document", "cb:fed:press", "cb:ecb:press", "world_event", "news",
           "fda:press", "fda:recall", "trial:update", "disclosure:ptr")


def _clean(v):
    return None if v is None or (isinstance(v, float) and v != v) else v


def docs_json(store, con, T):
    cited = set()
    since = (date.fromisoformat(T[:10]) - timedelta(days=90)).isoformat()
    for p in sorted((store.root / "brief").glob("*/*.json")):
        if p.stem < since:
            continue
        b = json.loads(p.read_text(encoding="utf-8")).get("brief", {})
        for sec in b.get("world", []) + b.get("sectors", []):
            cited |= set(sec.get("citations", []))
    recent = documents_as_of(con, (date.fromisoformat(T[:10]) - timedelta(days=14)).isoformat(), T)
    out = {}
    if len(recent):
        keep = recent[recent["kind"].isin(NOTABLE) | recent["doc_id"].isin(cited)]
        for d in keep.itertuples():
            out[d.doc_id] = {"title": _clean(d.title), "url": _clean(d.url), "source": d.source_id,
                             "kind": d.kind, "published_at": d.published_at}
    missing = sorted(cited - set(out))
    if missing:
        ph = ",".join("?" * len(missing))
        for d in con.execute(f"SELECT doc_id, title, url, source_id, kind, published_at FROM documents "
                             f"WHERE doc_id IN ({ph})", missing).df().itertuples():
            out[d.doc_id] = {"title": _clean(d.title), "url": _clean(d.url), "source": d.source_id,
                             "kind": d.kind, "published_at": d.published_at}
    return dict(sorted(out.items()))


def _latest(obs, sid, entity=None):
    s = obs[obs["series_id"] == sid]
    if entity:
        s = s[s["entity_id"] == entity]
    if not len(s):
        return None
    r = s.sort_values("obs_date").iloc[-1]
    return {"value": round(float(r["value"]), 6), "day": r["obs_date"]}


def world_json(con, T):
    obs = observations_as_of(con, T)
    facts = facts_as_of(con, T)
    countries = {}
    for cc, (name, lat, lon) in COUNTRY.items():
        c = {"name": name, "lat": lat, "lon": lon}
        for k in ("events", "conflict_share", "goldstein", "tone"):
            v = _latest(obs, f"gdelt:{k}", f"country:{cc}")
            if v:
                c[k], c["day"] = v["value"], v["day"]
        if len(facts):
            for role in ("head_of_state", "head_of_government"):
                f = facts[(facts["subject_id"] == f"country:{cc}") & (facts["predicate"] == role)]
                if len(f):
                    c[role] = sorted(set(f["value"].dropna()))
        countries[cc] = c
    rates = {k: _latest(obs, s) for k, s in (("ust_3m", "ust:3m"), ("ust_2y", "ust:2y"), ("ust_10y", "ust:10y"),
                                              ("ust_30y", "ust:30y"), ("estr", "ecb:estr"),
                                              ("euribor_3m", "ecb:euribor:3m"), ("fed_funds", "fred:DFF"))}
    fx = {k: _latest(obs, f"ecb:fx:{k}") for k in ("USD", "GBP", "JPY", "CNY", "CHF")}
    risk = {k: _latest(obs, s) for k, s in (("gpr", "gpr:daily"), ("epu", "epu:us_daily"))}
    ev = documents_as_of(con, (date.fromisoformat(T[:10]) - timedelta(days=3)).isoformat(), T, source_like="wikipedia")
    events = []
    if len(ev):
        for d in ev[ev["kind"] == "world_event"].tail(40).itertuples():
            extra = json.loads(d.extra) if isinstance(d.extra, str) else {}
            events.append({"doc_id": d.doc_id, "title": d.title, "day": extra.get("event_day"),
                           "topic": extra.get("topic")})
    return {"as_of": T, "countries": countries, "rates": {k: v for k, v in rates.items() if v},
            "fx_per_eur": {k: v for k, v in fx.items() if v}, "risk": {k: v for k, v in risk.items() if v},
            "events": events}


def graph_json(con, T, days=180):
    nodes, edges = {}, []
    sectors = {}
    for c in config.UNIVERSE["companies"]:
        nodes[f"co:{c['ticker']}"] = {"id": f"co:{c['ticker']}", "type": "company", "label": c["ticker"],
                                      "name": c["name"], "sector": c["sector"]}
        sid = f"sector:{c['sector']}"
        sectors[sid] = {"id": sid, "type": "sector", "label": c["sector"]}
        edges.append({"a": f"co:{c['ticker']}", "b": sid, "kind": "in_sector", "since": None})
    nodes.update(sectors)
    facts = facts_as_of(con, T)
    if len(facts):
        for r in facts[facts["predicate"].isin(["ceo", "chairperson"]) & facts["subject_id"].str.startswith("co:")].itertuples():
            nodes.setdefault(r.object_id, {"id": r.object_id, "type": "person", "label": _clean(r.value) or r.object_id})
            edges.append({"a": r.object_id, "b": r.subject_id, "kind": r.predicate, "since": r.valid_from[:10]})
        for r in facts[facts["predicate"].isin(["head_of_state", "head_of_government"])].itertuples():
            nodes.setdefault(r.subject_id, {"id": r.subject_id, "type": "country" if r.subject_id.startswith("country:") else "institution",
                                            "label": COUNTRY.get(r.subject_id.removeprefix("country:"), (r.subject_id,))[0]})
            nodes.setdefault(r.object_id, {"id": r.object_id, "type": "person", "label": _clean(r.value) or r.object_id})
            edges.append({"a": r.object_id, "b": r.subject_id, "kind": r.predicate, "since": r.valid_from[:10]})
    since = (date.fromisoformat(T[:10]) - timedelta(days=days)).isoformat()
    a = con.execute(f"""SELECT kind, person_id, person_name, ticker, action, size_high, traded_on, disclosed_at FROM alerts
                        WHERE disclosed_at <= '{T}' AND disclosed_at >= '{since}'
                        QUALIFY ROW_NUMBER() OVER (PARTITION BY alert_id ORDER BY recorded_at) = 1""").df()
    agg = {}
    for r in a.itertuples():
        k = (r.person_id, f"co:{r.ticker}", f"{r.kind}_{r.action}")
        g = agg.setdefault(k, {"n": 0, "value": 0.0, "since": r.traded_on, "name": r.person_name, "kind": r.kind})
        g["n"] += 1
        g["value"] += float(r.size_high or 0)
        g["since"] = min(g["since"], r.traded_on)
    for (pid, co, kind), g in agg.items():
        nodes.setdefault(pid, {"id": pid, "type": "member_of_congress" if g["kind"] == "congress" else "insider",
                               "label": g["name"]})
        edges.append({"a": pid, "b": co, "kind": kind, "since": g["since"], "count": g["n"],
                      "value_usd": round(g["value"], 2)})
    return {"as_of": T, "window_days": days, "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
            "edges": sorted(edges, key=lambda e: (e["kind"], e["a"], e["b"]))}


def run(store):
    T = utcnow()
    con = store.connect()
    site = store.root / "site"
    docs = docs_json(store, con, T)
    write_json(site / "docs.json", {"as_of": T, "docs": docs})
    world = world_json(con, T)
    write_json(site / "world.json", world)
    graph = graph_json(con, T)
    write_json(site / "graph.json", graph)
    return {"docs": len(docs), "countries": len(world["countries"]), "nodes": len(graph["nodes"]),
            "edges": len(graph["edges"])}
