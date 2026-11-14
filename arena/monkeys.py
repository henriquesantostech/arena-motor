"""Offline monkeys (design v2, section 8.2): 1,000 random portfolios with the agents' turnover.

Each offline monkey mirrors one agent (monkey i -> agent i mod 20). Every night it makes the same number of
moves as its agent: when the agent orders k full exits and e entries, the monkey sells k of its holdings and
buys e companies, all chosen at random, each entry sized at the same fraction of the portfolio as the agent's
matching entry. Same universe, same exclusions, same fills at the next open, same costs, dividends and splits.
Partial trims and top-ups are not mirrored (they are small next to entries and exits).

Nothing is stored but the results: the whole run is recomputed from the journal and the raw data every night,
and rows already stored must come out identical (a built-in replay check).

Archive outputs:
  monkeys/values.csv     date, then one column per monkey (m0000 … m0999), value in EUR at the close
  monkeys/summary.json   latest luck band and, for every agent, its percentile against the monkeys
"""
import hashlib
import json

import numpy as np
import pandas as pd

from . import config
from .market import apply_events, buy, fill_pending, new_participant, sell
from .view import View

N_MONKEYS = 1000


def _rng(i, day):
    return np.random.default_rng(int(hashlib.sha256(f"offline-{i:04d}|{day}".encode()).hexdigest()[:16], 16))


def _agents():
    return [p for p in config.POPULATION["participants"] if p["type"] == "agent"]


def _value(m, closes, last, rate):
    total = m["cash"]
    for t, p in m["positions"].items():
        c = closes.get(t, last.get(t, 0.0))
        total += p["shares"] * c / rate
    return round(total + 0.0, 2)


def simulate(archive, n=N_MONKEYS):
    """Returns a DataFrame indexed by date with one column per monkey."""
    agents = _agents()
    days = archive.journal_days()
    monkeys, rows, last = None, [], {}
    for d in days:
        j = archive.read_journal(d)
        view = View(archive, d, j["inputs"]["cutoff"])
        rate = j["market"]["eurusd"]
        today = view._by_day[d]
        closes = today["close"].to_dict()
        last.update(closes)
        if monkeys is None:
            monkeys = []
            for i in range(n):
                a = agents[i % len(agents)]
                monkeys.append(new_participant({"name": f"m{i:04d}", "type": "offline_monkey",
                                                "species": "Monkey", "dna": None,
                                                "copies_management_of": a["name"]}, d))
        else:
            events = view.events_on(d)
            for m in monkeys:
                apply_events(m, events, rate)
                fill_pending(m, view, d, rate)
            for t, when in j["state"]["delisted"].items():
                if when == d:
                    price = view.last_close(t)
                    for m in monkeys:
                        m["pending"] = [o for o in m["pending"] if o["ticker"] != t]
                        if t in m["positions"] and price:
                            sell(m, t, m["positions"][t]["shares"], price, rate, d)
        values = [_value(m, closes, last, rate) for m in monkeys]
        rows.append([d] + values)
        # decide tonight's moves, mirroring each agent's orders
        excluded = set(j["checks"]["excluded"]) | set(j["state"]["delisted"])
        eligible = sorted(t for t in j["signals"] if t not in excluded)
        plan = {}
        for a in agents:
            pa = j["state"]["participants"][a["name"]]
            av = j["values"][a["name"]]
            exits = sum(1 for o in pa["pending"] if o["side"] == "sell" and o.get("all"))
            entries = [o["eur"] / av for o in pa["pending"]
                       if o["side"] == "buy" and o.get("reason", {}).get("cause") == "entry" and av]
            plan[a["name"]] = (exits, entries)
        for i, m in enumerate(monkeys):
            exits, entries = plan[m["copies_management_of"]]
            if not exits and not entries:
                continue
            rng = _rng(i, d)
            held = sorted(m["positions"])
            out = [held[k] for k in sorted(rng.choice(len(held), size=min(exits, len(held)), replace=False))] if held and exits else []
            pool = [t for t in eligible if t not in m["positions"]]
            picks = [pool[k] for k in rng.choice(len(pool), size=min(len(entries), len(pool)), replace=False)] if pool and entries else []
            v = values[i]
            orders = [{"side": "sell", "ticker": t, "shares": m["positions"][t]["shares"], "all": True,
                       "reason": {"cause": "random"}} for t in out]
            orders += [{"side": "buy", "ticker": t, "eur": round(f * v, 2), "reason": {"cause": "random"}}
                       for t, f in zip(picks, entries)]
            m["pending"] = orders
    cols = ["date"] + [f"m{i:04d}" for i in range(n)]
    return pd.DataFrame(rows, columns=cols).set_index("date")


def run(archive, n=N_MONKEYS):
    """Recomputes every offline monkey, checks stored rows are unchanged, writes values and summary."""
    df = simulate(archive, n)
    out = archive.root / "monkeys"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "values.csv"
    changed = []
    if path.exists():
        old = pd.read_csv(path, dtype={"date": str}).set_index("date")
        common = [d for d in old.index if d in df.index]
        diff = (old.loc[common] - df.loc[common, old.columns]).abs().max(axis=1)
        changed = [d for d in common if diff[d] > 0.005]
    df.to_csv(path, lineterminator="\n", float_format="%.2f")
    summary = _summary(archive, df)
    summary["replay_identical"] = not changed
    summary["changed_dates"] = changed
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, allow_nan=False) + "\n",
                                      encoding="utf-8", newline="\n")
    return summary


def _summary(archive, df):
    if df.empty:
        return {"date": None}
    d = df.index[-1]
    rets = df.iloc[-1] / df.iloc[0] - 1
    j = archive.read_journal(d)
    first = archive.read_journal(df.index[0])
    agents = {}
    for a in _agents():
        name = a["name"]
        r = j["values"][name] / first["values"][name] - 1
        own = [c for i, c in enumerate(df.columns) if i % len(_agents()) == _agents().index(a)]
        agents[name] = {
            "return": round(r, 6),
            "percentile_vs_all_monkeys": round(float((rets < r).mean()), 4),
            "percentile_vs_mirroring_monkeys": round(float((rets[own] < r).mean()), 4),
        }
    q = rets.quantile([0.05, 0.5, 0.95]).round(6)
    band = (df.div(df.iloc[0]) - 1).quantile([0.05, 0.95], axis=1).T.round(6)
    return {
        "date": d, "start": df.index[0], "monkeys": int(df.shape[1]),
        "return_p05": float(q[0.05]), "return_median": float(q[0.5]), "return_p95": float(q[0.95]),
        "best_of_n": round(float(rets.max()), 6),
        "luck_band": {"dates": list(band.index), "p05": band[0.05].tolist(), "p95": band[0.95].tolist()},
        "agents": agents,
    }
