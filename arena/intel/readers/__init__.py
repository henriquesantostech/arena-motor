"""AI readers (design v2, section 9). Each reader turns work items into readings; every raw output is stored with
reader, version, model hash and runtime flags, so decisions recomputed from stored readings are bit-exact.

Flow on GitHub Actions: triage (one job) -> read (matrix: reader x shard) -> merge (one job).
  read  python -m arena.intel read --reader finbert|gliner|embed|llm --shard i --shards n --work W --models M
"""
import json
import time
from pathlib import Path

import pandas as pd

from ..store import SCHEMAS, Store, utcnow
from .llama import Server, cfg

LLM_SYSTEM = (
    "You read one financial or world-news item and return only JSON. Use only the text given; do not use outside "
    "knowledge about later events. Companies must be from the given candidate list (ticker symbols) or none. "
    "direction: +1 good for the company's shares, -1 bad, 0 neutral or unclear. magnitude: 0 none, 1 minor, "
    "2 notable, 3 major. horizon: days, weeks or months. novelty: 0 routine or already known, 1 genuinely new.")
EVENT_TYPES = ["earnings", "guidance", "merger_acquisition", "management_change", "product", "legal_regulatory",
               "government_policy", "macro_data", "monetary_policy", "geopolitics", "labor", "capital_return",
               "financing", "accident_disaster", "cybersecurity", "index_change", "other"]
LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "event_type": {"type": "string", "enum": EVENT_TYPES},
        "summary": {"type": "string", "maxLength": 200},
        "novelty": {"type": "integer", "enum": [0, 1]},
        "companies": {"type": "array", "maxItems": 5, "items": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}, "direction": {"type": "integer", "enum": [-1, 0, 1]},
                           "magnitude": {"type": "integer", "enum": [0, 1, 2, 3]},
                           "horizon": {"type": "string", "enum": ["days", "weeks", "months"]}},
            "required": ["ticker", "direction", "magnitude", "horizon"], "additionalProperties": False}},
    },
    "required": ["event_type", "summary", "novelty", "companies"], "additionalProperties": False,
}


def _items(work, shard, shards, only_llm=False):
    out = []
    p = Path(work) / "items.jsonl"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        it = json.loads(line)
        if it["shard"] % shards == shard and (not only_llm or it["llm"]):
            out.append(it)
    return out


def _row(doc_id, reader, rc, label=None, score=None, output=None, runtime=None, model_sha=None):
    return {"doc_id": doc_id, "reader": reader, "reader_version": rc["version"],
            "model_sha": model_sha or rc.get("sha256") or f"{rc['model']}@{rc.get('revision', '')}",
            "label": label, "score": score, "output": output, "recorded_at": utcnow(), "runtime": runtime}


def read_finbert(items, rc, models):
    from transformers import pipeline
    clf = pipeline("text-classification", model=rc["model"], revision=rc.get("revision"), top_k=None,
                   truncation=True, max_length=256, device=-1)
    rows = []
    for i in range(0, len(items), 32):
        batch = items[i:i + 32]
        res = clf([it["text"][:1000] for it in batch])
        for it, scores in zip(batch, res):
            s = {x["label"].lower(): round(float(x["score"]), 6) for x in scores}
            net = round(s.get("positive", 0) - s.get("negative", 0), 6)
            rows.append(_row(it["doc_id"], "finbert", rc, max(s, key=s.get), net, s))
    return rows


def read_gliner(items, rc, models):
    from gliner2 import AutoExtractor
    from ..entities import Linker
    model = AutoExtractor.from_pretrained(rc["model"])
    linker = Linker()
    rows = []
    for it in items:
        res = model.extract_entities(it["text"][:2000], rc["labels"])
        ents = res.get("entities", res) if isinstance(res, dict) else {}
        spans = {k: sorted(set(v))[:20] for k, v in ents.items() if v}
        linked = sorted({e for v in spans.values() for s in v for e in [linker.link_span(s)] if e})
        rows.append(_row(it["doc_id"], "gliner", rc, ",".join(linked)[:500] or None, float(len(linked)),
                         {"spans": spans, "linked": linked}))
    return rows


def read_embed(items, rc, models):
    rows = []
    with Server(models, rc["file"], embedding=True, port=8091, ctx=2048) as srv:
        for i in range(0, len(items), 16):
            batch = items[i:i + 16]
            vecs = srv.embed(["title: none | text: " + it["text"][:1500] for it in batch], rc["dims"])
            for it, v in zip(batch, vecs):
                rows.append(_row(it["doc_id"], "embed", rc, None, None, {"v": v}, srv.runtime))
    return rows


def read_llm(items, rc, models, budget_s=3000):
    from ... import config
    names = {c["ticker"]: c["name"] for c in config.UNIVERSE["companies"]}
    rows = []
    t0 = time.monotonic()
    with Server(models, rc["file"], port=8090, ctx=4096) as srv:
        for it in items:
            if time.monotonic() - t0 > budget_s:
                break
            cands = [e.removeprefix("co:") for e in it["entity_ids"] if e.startswith("co:")]
            cand_txt = ", ".join(f"{t} ({names.get(t, '')})" for t in cands) or "none detected; use none unless obvious"
            user = (f"Published: {it['published_at']}\nType: {it['kind']}\nCandidate companies: {cand_txt}\n\n"
                    f"Text:\n{it['text'][:5000]}")
            raw, timings = srv.chat(LLM_SYSTEM, user, LLM_SCHEMA, max_tokens=400)
            try:
                out = json.loads(raw)
                ok = True
            except json.JSONDecodeError:
                out, ok = {"raw": raw[:2000]}, False
            runtime = {**srv.runtime, "timings": {k: timings.get(k) for k in ("prompt_n", "predicted_n", "prompt_ms", "predicted_ms")
                                                  if isinstance(timings, dict)}}
            rows.append(_row(it["doc_id"], "llm", rc, out.get("event_type") if ok else "invalid_json",
                             float(len(out.get("companies", []))) if ok else None, out, runtime))
    return rows


READERS = {"finbert": read_finbert, "gliner": read_gliner, "embed": read_embed, "llm": read_llm}


def run_shard(store, reader, shard, shards, work, models):
    rc = cfg()["readers"][reader]
    work = Path(work) if work else store.root.parent.parent / "intel-work"
    items = _items(work, shard, shards, only_llm=(reader == "llm"))
    rows = READERS[reader](items, rc, models or "models") if items else []
    out = work / "out"
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=SCHEMAS["readings"])
    for c in ("output", "runtime"):
        df[c] = df[c].map(lambda v: None if v is None else json.dumps(v, ensure_ascii=False, sort_keys=True))
    df.to_parquet(out / f"{reader}-{shard}.parquet", index=False)
    return {"reader": reader, "shard": shard, "items": len(items), "readings": len(rows)}


def merge(store, work):
    work = Path(work or (store.root.parent.parent / "intel-work"))
    files = sorted((work / "out").glob("*.parquet")) if (work / "out").exists() else []
    n = 0
    for f in files:
        df = pd.read_parquet(f)
        n += store.add("readings", df)
    written = store.flush()
    return {"files": len(files), "readings": n, "rows": written}
