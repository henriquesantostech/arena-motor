"""Daily World Brief as of T (design v2, section 3.3), written by the pinned 9B model from knowledge-base facts and
documents with timestamps <= T only, with citations to document ids. Stored once per day and never regenerated.

The brief is an input to humans and the site. Its sector headwind/tailwind scores become the shadow signal
`brief_sector_tailwind`, which must pass the Signal Lab like any other.
"""
import json
import re
from datetime import date, timedelta

from ... import config
from ...archive import write_json
from ..store import utcnow
from ..wkb import documents_as_of, facts_as_of, next_weekday, observations_as_of
from .llama import Server, cfg

SECTORS = sorted({c["sector"] for c in config.UNIVERSE["companies"]})
SCHEMA = {   # property order = generation order: the short, structured parts come first so they are never cut
    "type": "object",
    "properties": {
        "headline": {"type": "string", "maxLength": 160},
        "sectors": {"type": "array", "minItems": len(SECTORS), "maxItems": len(SECTORS), "items": {
            "type": "object", "properties": {
                "sector": {"type": "string", "enum": SECTORS}, "score": {"type": "integer", "enum": [-2, -1, 0, 1, 2]},
                "reason": {"type": "string", "maxLength": 110},
                "citations": {"type": "array", "maxItems": 3, "items": {"type": "string"}}},
            "required": ["sector", "score", "reason", "citations"], "additionalProperties": False}},
        "markets": {"type": "string", "maxLength": 400},
        "world": {"type": "array", "maxItems": 6, "items": {
            "type": "object", "properties": {
                "topic": {"type": "string", "maxLength": 60}, "summary": {"type": "string", "maxLength": 300},
                "citations": {"type": "array", "maxItems": 4, "items": {"type": "string"}}},
            "required": ["topic", "summary", "citations"], "additionalProperties": False}},
        "watch": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 140}},
    },
    "required": ["headline", "sectors", "markets", "world", "watch"], "additionalProperties": False,
}
SYSTEM = ("You write the Daily World Brief of a paper-money research arena. Use ONLY the facts and documents "
          "given, all dated on or before the brief date; never add outside knowledge or later events. Be neutral "
          "and factual, no investment advice. Every world item and sector score must cite document ids from the "
          "list (the [id] prefixes). Sector score: -2 strong headwind, 0 neutral or no evidence, +2 strong "
          "tailwind, judged only from the evidence given; give a score for every sector. Put document ids only in the \"citations\" lists, never inside the text. Write in English.")


def _context(con, T):
    start = (date.fromisoformat(T[:10]) - timedelta(days=2)).isoformat()
    lines = ["## Market and macro state (latest known values)"]
    obs = observations_as_of(con, T)
    for sid, label in (("ust:2y", "US 2y yield %"), ("ust:10y", "US 10y yield %"), ("ecb:estr", "euro STR %"),
                       ("ecb:fx:USD", "EUR/USD"), ("fred:DFF", "Fed funds %"), ("fred:BAMLH0A0HYM2", "US HY spread %"),
                       ("fred:DCOILWTICO", "WTI oil $")):
        s = obs[obs["series_id"] == sid].sort_values("obs_date") if len(obs) else obs
        if len(s) >= 2:
            lines.append(f"- {label}: {s.iloc[-1]['value']:.3f} on {s.iloc[-1]['obs_date']} "
                         f"(5 obs earlier {s.iloc[max(0, len(s) - 6)]['value']:.3f})")
    leaders = facts_as_of(con, T)
    if len(leaders):
        l = leaders[leaders["predicate"].isin(["head_of_state", "head_of_government", "chairperson"]) &
                    leaders["subject_id"].str.startswith(("country:", "org:"))]
        lines.append("## Who governs (selection)")
        for r in l.sort_values(["subject_id", "predicate"]).head(40).itertuples():
            lines.append(f"- {r.subject_id} {r.predicate}: {r.value}")
    docs = documents_as_of(con, start, T)
    readings = con.execute("""SELECT doc_id, output FROM readings WHERE reader = 'llm'
                              QUALIFY ROW_NUMBER() OVER (PARTITION BY doc_id ORDER BY recorded_at DESC) = 1""").df()
    summ = {r.doc_id: json.loads(r.output).get("summary", "") for r in readings.itertuples()
            if r.output and r.output.startswith("{")}
    lines.append("## Documents (id | time | type | title or summary)")
    order = {"world_event": 0, "cb:fed:press": 1, "cb:ecb:press": 1, "fedreg:presidential_document": 1,
             "filing:8-K": 2, "news": 2}
    if len(docs):
        docs = docs.assign(o=docs["kind"].map(lambda k: order.get(k, 5))).sort_values(["o", "published_at", "doc_id"])
        for d in docs.head(100).itertuples():
            text = summ.get(d.doc_id) or d.title or ""
            lines.append(f"[{d.doc_id}] {d.published_at[:16]} {d.kind}: {text[:220]}")
    return "\n".join(lines), set(docs["doc_id"]) if len(docs) else set()


def schema_for(ids):
    """The answer schema with citations limited to the document ids in the context: the model cannot cite a document
    it was not given (the 2026-11-17 brief invented ten)."""
    import copy
    sc = copy.deepcopy(SCHEMA)
    if ids:
        item = {"type": "string", "enum": sorted(ids)}
        sc["properties"]["sectors"]["items"]["properties"]["citations"]["items"] = item
        sc["properties"]["world"]["items"]["properties"]["citations"]["items"] = item
    return sc


def _salvage(raw):
    """Keep the complete leading parts of a cut-off answer (headline, then every whole sector object), so the
    sector scores survive; the brief is marked partial and the raw text kept for audit."""
    out = {"invalid_json": raw[:4000], "partial": True}
    dec = json.JSONDecoder()
    m = re.search(r'"headline"\s*:\s*', raw)
    if m:
        try:
            out["headline"] = dec.raw_decode(raw, m.end())[0]
        except json.JSONDecodeError:
            pass
    i = raw.find('"sectors"')
    if i < 0:
        return out
    j = raw.find("[", i) + 1
    secs = []
    while j > 0:
        k = raw.find("{", j)
        if k < 0:
            break
        try:
            obj, j = dec.raw_decode(raw, k)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict) and obj.get("sector") in SECTORS and obj.get("score") in (-2, -1, 0, 1, 2):
            secs.append(obj)
        nxt = raw[j:].lstrip()
        if not nxt.startswith(","):
            break
    out["sectors"] = secs
    return out


def write_brief(store, models, T=None):
    T = T or utcnow()
    day = T[:10]
    path = store.root / "brief" / day[:4] / f"{day}.json"
    if path.exists() and "invalid_json" not in json.loads(path.read_text(encoding="utf-8")).get("brief", {}):
        return {"brief": "exists", "day": day}   # a cut-off brief of the same day may be retried once more
    rc = cfg()["readers"]["brief"]
    con = store.connect()
    ctx, ids = _context(con, T)
    with Server(models or "models", rc["file"], port=8092, ctx=16384) as srv:
        raw, timings = srv.chat(SYSTEM, f"Brief date (as of): {T}\n\n{ctx}", schema_for(ids), max_tokens=3200)
        runtime = srv.runtime
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        out = _salvage(raw)
    bad = sorted({c for sec in out.get("world", []) + out.get("sectors", []) for c in sec.get("citations", [])} - ids)
    brief = {"as_of": T, "model": rc["model"], "model_sha": rc["sha256"], "reader_version": rc["version"],
             "runtime": runtime, "documents_in_context": len(ids), "unknown_citations": bad, "brief": out}
    write_json(path, brief)
    # sector scores -> shadow signal rows (one per company of the sector)
    # dated for the next session whose decision can use it (today if a weekday, else the next weekday)
    sig_day = day if date.fromisoformat(day).weekday() < 5 else next_weekday(day)
    rows = []
    by_sector = {s["sector"]: s["score"] for s in out.get("sectors", [])}
    for c in config.UNIVERSE["companies"]:
        if c["sector"] in by_sector:
            rows.append({"date": sig_day, "ticker": c["ticker"], "signal_id": "intel.brief_sector_tailwind",
                         "value": float(by_sector[c["sector"]]), "published_at": T, "recorded_at": utcnow()})
    store.add("signals", rows)
    store.flush()
    return {"brief": "written", "day": day, "documents": len(ids), "unknown_citations": len(bad),
            "sectors": len(by_sector)}
