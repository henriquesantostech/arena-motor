"""Model admission exam (design v2, section 9): runs one reader on the frozen labelled exam and scores it.

  python -m arena.intel exam --reader llm --models M --work W [--archive A]

The result (scores, pass/fail per threshold, model hash, seconds per item) is written to
<archive>/intel/exam/<reader>-<date>.json when an archive is given, else to the work folder.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from ... import config
from ...archive import write_json
from . import READERS
from .llama import cfg

EXAM_DIR = config.RULES_DIR / "exam"


def load(version="v1"):
    items = [json.loads(l) for l in (EXAM_DIR / f"exam_{version}.jsonl").read_text(encoding="utf-8").splitlines()]
    meta = json.loads((EXAM_DIR / "exam.json").read_text(encoding="utf-8"))
    return items, meta


def _work_items(items):
    return [{"doc_id": it["id"], "kind": "exam", "published_at": "exam", "text": it["text"], "llm": True,
             "entity_ids": [f"co:{t}" for t in it["candidates"]], "shard": 0} for it in items]


def score_llm(items, rows):
    by = {r["doc_id"]: r for r in rows}
    valid = et = dir_ok = dir_n = tp = fp = fn = 0
    for it in items:
        r = by.get(it["id"])
        out = r["output"] if r else {}
        if not r or "event_type" not in out:
            fn += len(it["gold"]["tickers"])
            continue
        valid += 1
        et += out["event_type"] == it["gold"]["event_type"]
        got = {c["ticker"] for c in out.get("companies", [])}
        gold = set(it["gold"]["tickers"])
        tp += len(got & gold)
        fp += len(got - gold)
        fn += len(gold - got)
        if it["gold"]["direction"] is not None and it["candidates"]:
            dir_n += 1
            first = next((c for c in out.get("companies", []) if c["ticker"] == it["candidates"][0]), None)
            dir_ok += (first["direction"] if first else 0) == it["gold"]["direction"]
    n = len(items)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    return {"json_valid": round(valid / n, 3), "event_type_accuracy": round(et / n, 3),
            "direction_accuracy": round(dir_ok / dir_n, 3) if dir_n else None,
            "ticker_f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0}


def score_finbert(items, rows):
    by = {r["doc_id"]: r for r in rows}
    ok = n = 0
    for it in items:
        d = it["gold"]["direction"]
        if d is None or it["id"] not in by:
            continue
        lab = by[it["id"]]["label"]
        n += 1
        ok += {"positive": 1, "negative": -1}.get(lab, 0) == d
    return {"direction_accuracy": round(ok / n, 3) if n else None}


def score_gliner(items, rows):
    by = {r["doc_id"]: r for r in rows}
    hit = n = 0
    for it in items:
        for t in it["candidates"]:
            n += 1
            hit += f"co:{t}" in (by.get(it["id"], {}).get("output") or {}).get("linked", [])
    return {"ticker_recall": round(hit / n, 3) if n else None}


def score_embed(items, rows):
    import numpy as np
    by = {r["doc_id"]: np.array(r["output"]["v"]) for r in rows}
    ids = [it["id"] for it in items if it["id"] in by]
    m = np.stack([by[i] for i in ids])
    sim = m @ m.T
    np.fill_diagonal(sim, -1)
    et = {it["id"]: it["gold"]["event_type"] for it in items}
    same = [et[ids[i]] == et[ids[int(sim[i].argmax())]] for i in range(len(ids))]
    return {"same_topic_retrieval": round(sum(same) / len(same), 3)}


SCORERS = {"llm": score_llm, "finbert": score_finbert, "gliner": score_gliner, "embed": score_embed}
CHECKS = {"json_valid": ("json_valid_min", 1), "event_type_accuracy": ("event_type_accuracy_min", 1),
          "direction_accuracy": ("direction_accuracy_min", 1), "ticker_f1": ("ticker_f1_min", 1),
          "ticker_recall": ("ticker_recall_min", 1), "same_topic_retrieval": ("same_topic_retrieval_min", 1),
          "seconds_per_item": ("max_seconds_per_item", -1)}


def run_exam(store, reader, models, work, version="v1"):
    items, meta = load(version)
    rc = cfg()["readers"][reader]
    t0 = time.monotonic()
    rows = READERS[reader](_work_items(items), rc, models or "models")
    secs = (time.monotonic() - t0) / max(1, len(items))
    scores = SCORERS[reader](items, rows)
    scores["seconds_per_item"] = round(secs, 2)
    rules = meta["admission"].get(reader, {})
    passed = {}
    for k, v in scores.items():
        if k in CHECKS and CHECKS[k][0] in rules and v is not None:
            lim, sign = rules[CHECKS[k][0]], CHECKS[k][1]
            passed[k] = v >= lim if sign > 0 else v <= lim
    result = {"reader": reader, "model": rc["model"], "model_sha": rc.get("sha256"), "exam": version,
              "ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "items": len(items),
              "scores": scores, "thresholds": rules, "passed": passed, "admitted": all(passed.values()) if passed else False,
              "outputs": [{"id": r["doc_id"], "label": r["label"], "output": r["output"]} for r in rows]}
    base = store.root / "exam" if store else Path(work or ".")
    write_json(base / f"{reader}-{result['ran_at'][:10]}.json", result)
    return {"reader": reader, "scores": scores, "admitted": result["admitted"]}
