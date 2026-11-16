"""Source adapters of the intelligence layer. One module per source, registered in rules/sources_intel.json.

Adapter contract (every module):
  SOURCE_ID = "<id in the registry>"
  def ingest(ctx) -> dict      fetches what is new, archives raw bytes, appends WKB rows; returns counts only
Optional:
  def backfill(ctx, start) -> dict

An adapter never raises into the night: the runner isolates failures, logs "error <type>" and moves on.
"""
import importlib
import json
import os
import time
import traceback
from dataclasses import dataclass, field

from ... import config
from ..entities import Linker
from ..store import Store, utcnow

REGISTRY_FILE = config.RULES_DIR / "sources_intel.json"


def registry():
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))["sources"]


def entry(source_id):
    for s in registry():
        if s["id"] == source_id:
            return s
    raise KeyError(source_id)


@dataclass
class Context:
    store: Store
    now: str = field(default_factory=utcnow)
    linker: Linker = None
    backfill_from: str = None      # set by the backfill command
    budget_s: float = 600          # wall-time budget per adapter
    detail: bool = False
    budget_override: float = None  # backfill: one budget for every adapter
    started: float = field(default_factory=time.monotonic)

    def key(self, name):
        return os.environ.get(name) or None

    def out_of_time(self):
        return time.monotonic() - self.started > self.budget_s


def run(ctx, only=None, skip=None, mode="ingest"):
    """Runs every enabled adapter (or the ones named). Returns {source_id: summary}."""
    results = {}
    # one wall-time budget for the whole ingest; each adapter gets min(its own budget, what is left).
    # Adapters stop cleanly when out of time and resume from their cursors the next night.
    total = float(os.environ.get("INTEL_INGEST_BUDGET_S", 0) or 0) or None
    t_start = time.monotonic()
    for s in registry():
        sid = s["id"]
        if only and sid not in only:
            continue
        if skip and sid in skip:
            continue
        if not s.get("enabled", True) and not only:
            results[sid] = "disabled"
            continue
        needs = s.get("env_key")
        if needs and not os.environ.get(needs):
            results[sid] = f"skipped (no {needs})"
            continue
        mod = importlib.import_module(s["adapter"].replace("/", ".").removesuffix(".py"))
        fn = getattr(mod, mode, None)
        if fn is None:
            results[sid] = f"no {mode}"
            continue
        ctx.started = time.monotonic()
        ctx.budget_s = float(ctx.budget_override or s.get("budget_s", 600))
        if total:
            left = total - (time.monotonic() - t_start)
            if left < 30:
                results[sid] = "skipped (night budget used)"
                continue
            ctx.budget_s = min(ctx.budget_s, left)
        t0 = time.monotonic()
        try:
            r = fn(ctx)
            results[sid] = {"ok": True, **(r or {}), "s": round(time.monotonic() - t0, 1)}
        except Exception as e:   # isolate: one source never stops the night
            results[sid] = {"ok": False, "error": type(e).__name__, "s": round(time.monotonic() - t0, 1)}
            if ctx.detail:
                traceback.print_exc()
    return results
