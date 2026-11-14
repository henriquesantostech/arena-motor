"""Daily World Brief as of T (design v2, section 3.3), written by the pinned 9B model from knowledge-base facts and
documents with timestamps <= T only, with citations to document ids. Stored once per day and never regenerated.

The brief is an input to humans and the site. Its sector headwind/tailwind scores become the shadow signal
`brief_sector_tailwind`, which must pass the Signal Lab like any other.
"""
import json
from datetime import date, timedelta

from ... import config
from ...archive import write_json
from ..store import utcnow
from ..wkb import documents_as_of, facts_as_of, next_weekday, observations_as_of
from .llama import Server, cfg

SECTORS = sorted({c["sector"] for c in config.UNIVERSE["companies"]})
SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "maxLength": 200},
        "world": {"type": "array", "maxItems": 8, "items": {
            "type": "object", "properties": {
                "topic": {"type": "string", "maxLength": 60}, "summary": {"type": "string", "maxLength": 400},
                "citations": {"type": "array", "maxItems": 5, "items": {"type": "string"}}},
            "required": ["topic", "summary", "citations"], "additionalProperties": False}},
        "markets": {"type": "string", "maxLength": 500},
        "sectors": {"type": "array", "maxItems": len(SECTORS), "items": {
            "type": "object", "properties": {
                "sector": {"type": "string", "enum": SECTORS}, "score": {"type": "integer", "enum": [-2, -1, 0, 1, 2]},
                "reason": {"type": "string", "maxLength": 240},
                "citations": {"type": "array", "maxItems": 4, "items": {"type": "string"}}},
            "required": ["sector", "score", "reason", "citations"], "additionalProperties": False}},
        "watch": {"type": "array", "maxItems": 5, "items": {"type": "string", "maxLength": 160}},
    },
    "required": ["headline", "world", "markets", "sectors", "watch"], "additionalProperties": False,
}
SYSTEM = ("You write the Daily World Brief of a paper-money research arena. Use ONLY the facts and documents "
          "given, all dated on or before the brief date; never add outside knowledge or later events. Be neutral "
          "and factual, no investment advice. Every world item and sector score must cite document ids from the "
          "list (the [id] prefixes). Sector score: -2 strong headwind, 0 neutral or no evidence, +2 strong "
          "tailwind, judged only from the evidence given. Write in English.")


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
        for d in docs.head(160).itertuples():
            text = summ.get(d.doc_id) or d.title or ""
            lines.append(f"[{d.doc_id}] {d.published_at[:16]} {d.kind}: {text[:220]}")
    return "\n".join(lines), set(docs["doc_id"]) if len(docs) else set()


def write_brief(store, models, T=None):
    T = T or utcnow()
    day = T[:10]
    path = store.root / "brief" / day[:4] / f"{day}.json"
    if path.exists():
        return {"brief": "exists", "day": day}
    rc = cfg()["readers"]["brief"]
    con = store.connect()
    ctx, ids = _context(con, T)
    with Server(models or "models", rc["file"], port=8092, ctx=12288) as srv:
        raw, timings = srv.chat(SYSTEM, f"Brief date (as of): {T}\n\n{ctx}", SCHEMA, max_tokens=1800)
        runtime = srv.runtime
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        out = {"invalid_json": raw[:4000]}
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
