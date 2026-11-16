"""Technical rehearsal of evolution on price history (never evidence).

Runs the real engine over past prices with every current rule applied from day zero (rules 1.1 DNA fields
and rules 1.2 evolution), then the offline monkeys, the ghost worlds and the merit statistics. The archive is
marked `"rehearsal": true`, so every report says "technical rehearsal ... never evidence". The universe is
today's S&P 100, so the history is survivorship-biased: it tests the machinery, not the strategies.

  python phase3/rehearsal.py --archive <empty folder> --day-zero 2024-01-31
  (again with the same folder: continues where it stopped, without fetching)
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from arena import config, evolution, merit, monkeys  # noqa: E402
from arena.archive import Archive  # noqa: E402
from arena.night import fetch, process  # noqa: E402


def rules_from(day_zero):
    """Every current rule applies from day zero (in memory only; the rules files are not touched)."""
    for u in config.RULES.get("dna_updates", []):
        u["effective_from"] = min(u["effective_from"], day_zero)
    evolution.RULES["effective_from"] = day_zero


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", required=True)
    ap.add_argument("--day-zero", default="2024-01-31")
    ap.add_argument("--until")
    ap.add_argument("--worlds", type=int, default=evolution.RULES["null_evolution"]["worlds"])
    a = ap.parse_args(argv)
    archive = Archive(a.archive)
    if not (archive.root / "arena.json").exists():
        archive.write_cfg({
            "name": "Arena of Agents: evolution rehearsal", "mode": "trial", "rehearsal": True,
            "day_zero": a.day_zero, "universe_frozen_on": config.UNIVERSE["frozen_on"],
            "note": ("Technical rehearsal on price history: every current rule applied from day zero; today's "
                     "universe (survivorship-biased). Tests the machinery only; never evidence."),
        })
        start = (pd.Timestamp(a.day_zero) - pd.Timedelta(days=430)).date().isoformat()
        r = fetch(archive, history_from=start)
        print(f"history from {start}: {r['prices']} price rows, until {r['until']}")
    day_zero = archive.cfg["day_zero"]
    rules_from(day_zero)
    t = time.time()
    done = process(archive, a.until, on_done=lambda d, p: print(d, "evolution" if "evolution" in p else "", flush=True)
                   if "evolution" in p or d.endswith("-01") else None)
    print(f"{len(done)} nights processed in {time.time() - t:.0f}s")
    t = time.time()
    m = monkeys.run(archive)
    print(f"offline monkeys: {m.get('monkeys')} ({time.time() - t:.0f}s)")
    t = time.time()
    r = evolution.run(archive, a.worlds)
    print(f"evolution: {r} ({time.time() - t:.0f}s)")
    t = time.time()
    rep = merit.run(archive)
    print(f"merit: {json.dumps(rep['trials'])} ({time.time() - t:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
