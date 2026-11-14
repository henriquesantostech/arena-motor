"""Arena commands.  Usage:  python -m arena <command> --archive <archive folder>

  create    creates a new arena in the archive (day zero + price history for the signals)
  fetch     appends new data to the archive (Yahoo, ECB, Tiingo)
  process   processes the missing trading days (without fetching)
  night     fetch + process + site  (what runs on GitHub every night)
  replay    replays a night and confirms it gives exactly the same result
  site      builds the site from the journal
  audit     one participant's accounts, step by step, to check by hand
  sources   lists the registered data sources and their terms
  monkeys   1,000 offline monkeys with the agents' turnover (luck band, best of N)
  lab       Signal Lab: daily IC and admission gates for every signal (shadow only)
"""
import argparse
import random
import sys
import traceback
from datetime import datetime, timezone

import pandas as pd

from . import config
from .archive import Archive


def main(argv=None):
    ap = argparse.ArgumentParser(prog="arena", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["create", "fetch", "process", "night", "replay", "site", "audit", "sources", "lab", "monkeys"])
    ap.add_argument("--archive", help="private archive folder")
    ap.add_argument("--day-zero", help="create: last trading day before the first trading day")
    ap.add_argument("--mode", default="trial", choices=["trial", "official"])
    ap.add_argument("--until", help="process: only up to this day")
    ap.add_argument("--date", help="replay: day to replay")
    ap.add_argument("--random", action="store_true", help="replay: a random day")
    ap.add_argument("--participant", help="audit: participant name")
    ap.add_argument("--out", help="audit: output CSV file")
    ap.add_argument("--detail", action="store_true", help="show the full error (local use only)")
    a = ap.parse_args(argv)
    if a.command == "sources":
        from . import sources
        for s in sources.registry():
            role = ", ".join(s.get("role") or ["(extension)"])
            print(f"{s['id']:<14} {role}  |  use: {s['use']}  |  {s['license']}")
        problems = sources.validate_registry()
        print("registry: OK" if not problems else "registry problems:\n  " + "\n  ".join(problems))
        return 0 if not problems else 1
    if not a.archive:
        ap.error("--archive is required")
    archive = Archive(a.archive)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    try:
        if a.command == "create":
            return create(archive, a.day_zero, a.mode)
        if a.command == "fetch":
            from .night import fetch
            r = fetch(archive)
            print(f"data until {r['until']}: {r['prices']} price rows, {r['events']} events, {r['fx']} FX rates, {r['tiingo']} cross-checks")
            return 0
        if a.command == "process":
            from .night import process
            days = process(archive, a.until)
            print(f"{len(days)} days processed" + (f" ({days[0]} to {days[-1]})" if days else ""))
            return 0
        if a.command == "night":
            return night(archive, now)
        if a.command == "replay":
            return replay(archive, a.date, a.random, now)
        if a.command == "site":
            from .site import build
            build(archive)
            print("site built")
            return 0
        if a.command == "monkeys":
            from .monkeys import run as run_monkeys
            m = run_monkeys(archive)
            print(f"offline monkeys: {m.get('monkeys', 0)}, up to {m.get('date')}, replay identical: {m.get('replay_identical')}")
            return 0 if m.get("replay_identical", True) else 1
        if a.command == "lab":
            from .lab import run as run_lab
            rep = run_lab(archive)
            for sid, r in rep["signals"].items():
                print(f"{sid:<22} {r['status']:<13} obs={r.get('observations')} mean_ic={r.get('mean_ic')} nw_t={r.get('nw_t')}")
            return 0
        if a.command == "audit":
            from .audit import audit
            print(audit(archive, a.participant, a.out))
            return 0
    except Exception as e:  # public logs only show the error type and message
        print(f"ERROR: {type(e).__name__}: {e}")
        if a.detail:
            traceback.print_exc()
        try:
            archive.log(f"{now},{a.command},,error {type(e).__name__}")
        except Exception:
            pass
        return 1


def create(archive, day_zero, mode):
    if not day_zero:
        raise SystemExit("missing --day-zero")
    if (archive.root / "arena.json").exists():
        raise SystemExit("this archive already has an arena")
    from .night import fetch
    archive.write_cfg({"name": "Arena of Agents", "mode": mode, "day_zero": day_zero,
                       "universe_frozen_on": config.UNIVERSE["frozen_on"],
                       "created_on": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                       "note": "Trial: results are wiped at the official start (kept separately)." if mode == "trial" else ""})
    start = (pd.Timestamp(day_zero) - pd.Timedelta(days=430)).date().isoformat()
    r = fetch(archive, history_from=start)
    print(f"arena created (day zero {day_zero}); history from {start}: {r['prices']} price rows")
    return 0


def night(archive, now):
    from .night import fetch, process
    r = fetch(archive)
    days = process(archive)
    site_ok = True
    try:
        from .monkeys import run as run_monkeys
        m = run_monkeys(archive)
        print(f"offline monkeys: {m.get('monkeys', 0)}, replay identical: {m.get('replay_identical')}")
    except Exception as e:   # the offline monkeys never stop the night
        print(f"offline monkeys not run: {type(e).__name__}")
    try:
        from .lab import run as run_lab
        lab = run_lab(archive)
        print(f"lab: {len(lab['signals'])} signals evaluated")
    except Exception as e:   # the shadow lab never stops the night
        print(f"lab not run: {type(e).__name__}")
    try:
        from .site import build
        build(archive)
    except Exception as e:   # the site never stops the night
        site_ok = False
        print(f"site not built: {type(e).__name__}")
    res = f"ok: data until {r['until']}, {len(days)} nights processed"
    if days:
        last = archive.read_journal(days[-1])
        n_orders = sum(len(p["pending"]) for p in last["state"]["participants"].values())
        n_exc = len(last["checks"]["excluded"])
        res += f", last {days[-1]}: {n_orders} orders for tomorrow, {n_exc} companies set aside"
    print(res)
    archive.log(f"{now},night,{len(days)},ok" + ("" if site_ok else " (site failed)"))
    return 0


def replay(archive, date, at_random, now):
    from .night import replay as replay_day
    days = archive.journal_days()
    if not days:
        print("no nights to replay yet")
        return 0
    if at_random:
        date = random.Random(now[:10]).choice(days)
    r = replay_day(archive, date)
    if r["identical"]:
        print(f"replay {r['day']}: identical")
        archive.log(f"{now},replay {r['day']},1,identical")
        return 0
    note = "" if r["stored_code"] == r["current_code"] else f" (code changed: {r['stored_code']} -> {r['current_code']})"
    print(f"replay {r['day']}: DIFFERENT in {', '.join(r['differences'])}{note}")
    archive.log(f"{now},replay {r['day']},1,different")
    return 1


if __name__ == "__main__":
    sys.exit(main())
