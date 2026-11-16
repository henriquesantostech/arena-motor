"""Triage: picks the documents the readers will process tonight and writes the shard work list.

All new documents go to the encoders (FinBERT, GLiNER2, embeddings). The LLM gets at most `max_items` of them,
chosen by a fixed, explainable priority (universe company mentioned, document type), ties broken by doc_id.
For 8-K filings the press release text (exhibit 99) is fetched from EDGAR and archived; other items use their
title and stored summary. The work list holds text only in the private work folder, never in public logs.
"""
import hashlib
import json
import re
from html import unescape
from pathlib import Path

from .. import http
from .llama import cfg

KIND_WEIGHT = {"filing:8-K": 3, "filing:8-K/A": 1, "fedreg:presidential_document": 3, "cb:fed:press": 3,
               "cb:ecb:press": 2, "news": 2, "world_event": 2, "fedreg:rule": 1, "fedreg:public_inspection": 1,
               "filing:10-Q": 1, "filing:10-K": 1, "fda:press": 2, "social:hn": 1}
MAX_ENCODER_ITEMS = 1500   # per night; the rest (lowest priority) waits, within the 3-day window
IMPORTANT_ITEMS = {"1.01", "1.02", "1.05", "2.01", "2.02", "2.05", "2.06", "3.01", "4.02", "5.01", "5.02", "7.01", "8.01"}


def shard_of(doc_id, shards):
    return int(hashlib.sha256(doc_id.encode()).hexdigest()[:8], 16) % shards


def work_dir(store, work=None):
    p = Path(work) if work else store.root.parent.parent / "intel-work"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _html_text(b):
    t = b.decode("utf-8", "ignore")
    t = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t)).strip()


def _press_release(store, doc):
    """Text of exhibit 99 (or the main document) of an 8-K, first 6,000 characters."""
    m = re.search(r"/data/(\d+)/(\d{18})/", doc["url"] or "")
    if not m:
        return ""
    base = f"https://www.sec.gov/Archives/edgar/data/{m.group(1)}/{m.group(2)}/"
    try:
        r, _, _ = http.fetch(store, "sec_edgar", base + "index.json")
        files = [f["name"] for f in r.json().get("directory", {}).get("item", [])]
        ex = sorted(f for f in files if re.search(r"ex-?99", f, re.I) and f.lower().endswith((".htm", ".html", ".txt")))
        target = ex[0] if ex else doc["url"].rsplit("/", 1)[-1]
        r, _, _ = http.fetch(store, "sec_edgar", base + target)
        return _html_text(r.content)[:6000]
    except http.FetchError:
        return ""


def _j(v, default):
    """JSON text column -> value; empty (None/NaN) -> default."""
    return json.loads(v) if isinstance(v, str) and v else default


def priority(doc):
    w = KIND_WEIGHT.get(doc["kind"], 0)
    ents = _j(doc["entity_ids"], [])
    w += 3 * any(e.startswith("co:") for e in ents)
    extra = _j(doc["extra"], {})
    if doc["kind"].startswith("filing:8-K"):
        items = set(extra.get("items") or [])
        w += 2 * bool(items & IMPORTANT_ITEMS) - 3 * (items <= {"9.01", "5.07", "5.03"})
    return w


def triage(store, shards=4, work=None):
    wd = work_dir(store, work)
    # every document recorded in the last 3 days that has no reading yet (failed nights are retried)
    from datetime import datetime, timedelta, timezone
    cursor = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = store.connect()
    docs = con.execute(f"""SELECT * FROM documents WHERE recorded_at > '{cursor}'
                           AND kind NOT IN ('filing:4', 'filing:4/A', 'filing:144')
                           QUALIFY ROW_NUMBER() OVER (PARTITION BY doc_id ORDER BY recorded_at) = 1
                           ORDER BY doc_id""").df()
    already = set()
    if store.has("readings"):
        already = set(con.execute("SELECT DISTINCT doc_id FROM readings").df()["doc_id"])
    docs = docs[~docs["doc_id"].isin(already)]
    max_llm = cfg()["readers"]["llm"]["max_items"]
    recs = docs.to_dict("records")
    for d in recs:
        d["priority"] = priority(d)
    ranked = sorted(recs, key=lambda d: (-d["priority"], d["doc_id"]))
    llm_ids = {d["doc_id"] for d in ranked[:max_llm] if d["priority"] >= 3}
    n = 0
    with open(wd / "items.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for d in ranked[:MAX_ENCODER_ITEMS]:
            text = d["title"] if isinstance(d["title"], str) else ""
            if d["doc_id"] in llm_ids and d["kind"].startswith("filing:8-K"):
                body = _press_release(store, d)
                if body:
                    text = f"{text}\n{body}"
            f.write(json.dumps({"doc_id": d["doc_id"], "kind": d["kind"], "published_at": d["published_at"],
                                "entity_ids": _j(d["entity_ids"], []), "text": text,
                                "llm": d["doc_id"] in llm_ids, "shard": shard_of(d["doc_id"], shards)},
                               ensure_ascii=False) + "\n")
            n += 1
    store.flush()   # archived exhibit fetches
    return {"items": n, "llm_items": len(llm_ids), "shards": shards}
