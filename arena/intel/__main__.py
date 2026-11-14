"""Intelligence layer commands.  Usage:  python -m arena.intel <command> --archive <archive folder>

  sources    lists the intel sources and their terms
  ingest     runs the source adapters (all enabled, or --only a,b)
  backfill   one-off history load for the adapters that support it (--from YYYY-MM-DD)
  triage     picks the documents for the LLM readers and writes the work list (shards)
  read       runs the readers on one shard (--reader finbert|gliner|embed|llm --shard i --shards n)
  merge      merges shard outputs into the readings table
  brief      writes the Daily World Brief (9B model)
  people     politicians and insiders: alerts and the Mirror shadow book
  signals    computes all shadow signals for the missing days
  lab        provisional Signal Lab report (rank IC per shadow signal)
  exam       model admission exam (--reader ...)
  status     counts per table (no data printed)

Public logs only print counts and "ok/error"; never data.
"""
import argparse
import json
import sys
import time
import traceback

from .store import Store, utcnow


def main(argv=None):
    ap = argparse.ArgumentParser(prog="arena.intel", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["sources", "ingest", "backfill", "triage", "read", "merge", "brief", "people",
                                        "signals", "lab", "exam", "status"])
    ap.add_argument("--archive")
    ap.add_argument("--only", help="comma-separated source ids")
    ap.add_argument("--skip", help="comma-separated source ids")
    ap.add_argument("--from", dest="start", help="backfill start date")
    ap.add_argument("--reader")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--work", help="folder for shard work files (default <archive>/../intel-work)")
    ap.add_argument("--models", help="folder with model files (default ./models)")
    ap.add_argument("--budget", type=float, help="seconds per adapter (backfill)")
    ap.add_argument("--run-id", help="partition suffix (defaults to the time)")
    ap.add_argument("--detail", action="store_true", help="full errors (local use only)")
    a = ap.parse_args(argv)

    if a.command == "sources":
        from .sources import registry
        for s in registry():
            print(f"{s['id']:<16} {'on ' if s.get('enabled', True) else 'off'} | {s['use']:<10} | {s['license']}")
        return 0
    if not a.archive and not (a.command in ("read", "exam") and a.work):
        ap.error("--archive is required")
    store = Store(a.archive, a.run_id) if a.archive else None
    t0 = time.monotonic()
    try:
        out = dispatch(a, store)
        print(json.dumps({"command": a.command, "ok": True, "s": round(time.monotonic() - t0, 1), **(out or {})},
                         sort_keys=True, default=str))
        return 0
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {str(e)[:200]}")
        if a.detail:
            traceback.print_exc()
        return 1


def dispatch(a, store):
    only = a.only.split(",") if a.only else None
    skip = a.skip.split(",") if a.skip else None
    if a.command in ("ingest", "backfill"):
        from .entities import Linker, universe_entities
        from .sources import Context, run
        ctx = Context(store=store, linker=Linker(), backfill_from=a.start, detail=a.detail, budget_override=a.budget)
        if not store.has("entities"):
            store.add("entities", universe_entities())
        res = run(ctx, only=only, skip=skip, mode="backfill" if a.command == "backfill" else "ingest")
        written = store.flush()
        return {"sources": res, "rows": written}
    if a.command == "status":
        con = store.connect()
        from .store import SCHEMAS
        return {"rows": {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in SCHEMAS}}
    if a.command == "triage":
        from .readers.triage import triage
        return triage(store, a.shards, a.work)
    if a.command == "read":
        from .readers import run_shard
        return run_shard(store, a.reader, a.shard, a.shards, a.work, a.models)
    if a.command == "merge":
        from .readers import merge
        return merge(store, a.work)
    if a.command == "brief":
        from .readers.brief import write_brief
        return write_brief(store, a.models)
    if a.command == "people":
        from .people import run as people_run
        return people_run(store)
    if a.command == "signals":
        from .shadow import compute_all
        return compute_all(store)
    if a.command == "lab":
        from .lab import report
        return report(store)
    if a.command == "exam":
        from .readers.exam import run_exam
        return run_exam(store, a.reader, a.models, a.work)
    raise SystemExit(f"unknown command {a.command}")


if __name__ == "__main__":
    sys.exit(main())
