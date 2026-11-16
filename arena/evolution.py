"""Evolution (rules/evolution.json): monthly selection, graveyard, births, family tree; and null evolution.

`apply()` is the only hook into the night (`night.process_day`). It acts only on evaluation days (first
trading day of a month, on or after the rules' effective date, with at least one agent old enough); on
every other night it returns None and changes nothing, so past nights replay identically.

`select_and_breed()` is shared by the arena and by the null-evolution worlds (ghosts), so both follow
exactly the same rules.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .market import new_participant

RULES = json.loads((config.RULES_DIR / "evolution.json").read_text(encoding="utf-8"))
GRIDS = RULES["birth"]["grids"]
MANAGEMENT = list(GRIDS)
ADMITTED = RULES["birth"]["admitted_signals"]
SIGNALS = config.SIGNALS
INDEX_NAME = "S&P 500 (EUR)"


# --- calendar ---------------------------------------------------------------------------------------------
def month_index(day):
    return int(day[:4]) * 12 + int(day[5:7])


def is_first_trading_day_of_month(day, trading_days):
    prev = [d for d in trading_days if d < day]
    return bool(prev) and prev[-1][:7] != day[:7]


def life_start(born, trading_days):
    after = [d for d in trading_days if d > born]
    return after[0] if after else None


def is_eligible(born, day, trading_days):
    if trading_days and born < trading_days[0]:
        return True   # born before the visible window (over a year ago)
    start = life_start(born, trading_days)
    return start is not None and month_index(day) - month_index(start) >= RULES["calendar"]["eligible_after_months"]


# --- random draws -----------------------------------------------------------------------------------------
def rng_for(text):
    return np.random.default_rng(int(hashlib.sha256(text.encode()).hexdigest()[:16], 16))


# --- DNA operations ---------------------------------------------------------------------------------------
def to_hundred(raw):
    """Non-negative numbers on the admitted signals -> integers adding up to 100 (largest remainder)."""
    total = sum(raw[s] for s in ADMITTED)
    if total <= 0:
        return None
    exact = {s: raw[s] * 100 / total for s in ADMITTED}
    out = {s: int(math.floor(exact[s] + 1e-12)) for s in ADMITTED}
    left = 100 - sum(out.values())
    order = sorted(ADMITTED, key=lambda s: (-(exact[s] - out[s]), ADMITTED.index(s)))
    for s in order[:left]:
        out[s] += 1
    return {s: out.get(s, 0) for s in SIGNALS}


def _grid_pos(gene, value):
    grid = GRIDS[gene]
    if value in grid:
        return grid.index(value)
    if value is None:
        return 0
    nums = [(abs(g - value), i) for i, g in enumerate(grid) if g is not None]
    return min(nums)[1]


def repair(dna):
    n = dna["n_holdings"]
    floor = math.ceil(100 / n) / 100
    cap = config.PORTFOLIO["max_weight_global"]
    dna["max_weight"] = round(min(max(dna["max_weight"], floor), cap), 2)
    return dna


def crossover_and_mutate(a, b, rng):
    """Child DNA from parents a (better ranked) and b. Draw order: weight genes, management genes,
    weight mutation, management mutation."""
    pick_w = rng.random(len(SIGNALS)) < 0.5
    pick_m = rng.random(len(MANAGEMENT)) < 0.5
    weights = {s: (b if pick_w[i] else a)["weights"].get(s, 0) for i, s in enumerate(SIGNALS)}
    mgmt = {g: (b if pick_m[i] else a).get(g) for i, g in enumerate(MANAGEMENT)}
    steps = rng.integers(-5, 6, size=len(ADMITTED))
    mutated = {s: weights[s] for s in SIGNALS}
    for s, k in zip(ADMITTED, steps):
        mutated[s] = max(0, weights[s] + int(k))
    for s in SIGNALS:
        if s not in ADMITTED:
            mutated[s] = 0
    new_w = to_hundred(mutated) or {s: (a["weights"].get(s, 0) if s in ADMITTED else 0) for s in SIGNALS}
    moves = rng.random(len(MANAGEMENT))
    ups = rng.random(len(MANAGEMENT)) < 0.5
    for i, g in enumerate(MANAGEMENT):
        pos = _grid_pos(g, mgmt[g])
        if moves[i] < 0.25:
            pos = min(len(GRIDS[g]) - 1, pos + 1) if ups[i] else max(0, pos - 1)
        mgmt[g] = GRIDS[g][pos]
    return repair({"weights": new_w, **mgmt})


def immigrant_dna(rng):
    raw = rng.dirichlet(np.ones(len(ADMITTED)))
    weights = to_hundred({s: float(x) for s, x in zip(ADMITTED, raw)})
    mgmt = {g: GRIDS[g][int(rng.integers(0, len(GRIDS[g])))] for g in MANAGEMENT}
    return repair({"weights": weights, **mgmt})


def species_centroids():
    out = {}
    for sp in config.POPULATION["species"]:
        ws = [p["dna"]["weights"] for p in config.POPULATION["participants"] if p["type"] == "agent" and p["species"] == sp]
        if ws:
            out[sp] = np.array([np.mean([w.get(s, 0) for w in ws]) for s in SIGNALS])
    return out


def nearest_species(weights):
    v = np.array([weights.get(s, 0) for s in SIGNALS], dtype=float)
    best, score = None, -2.0
    for sp, c in species_centroids().items():   # population.json species order breaks ties
        cos = float(v @ c / (np.linalg.norm(v) * np.linalg.norm(c))) if np.linalg.norm(v) and np.linalg.norm(c) else -1.0
        if cos > score + 1e-12:
            best, score = sp, cos
    return best


def gene_delta(child, parents):
    """Child DNA minus the parents' mean (weights in points) and the management genes that changed."""
    w = {s: round(child["weights"].get(s, 0) - float(np.mean([p["weights"].get(s, 0) for p in parents])), 1)
         for s in SIGNALS if s in ADMITTED}
    m = {g: {"from": parents[0].get(g), "to": child[g]} for g in MANAGEMENT if child[g] != parents[0].get(g)}
    return {"weights": w, "management": m}


# --- identity -------------------------------------------------------------------------------------------------
def founder_slots():
    agents = [p["name"] for p in config.POPULATION["participants"] if p["type"] == "agent"]
    return {n: i for i, n in enumerate(agents)}


def identity(part):
    """generation, cohort, slot of any agent (founders have no stored fields)."""
    return {"generation": part.get("generation", 1), "cohort": part.get("cohort", 0),
            "slot": part.get("slot", founder_slots().get(part["name"])), "immigrant": part.get("immigrant", False)}


def next_name(species, taken):
    prefix = config.POPULATION["species"][species]["prefix"]
    nums = [int(n.split("-")[-1]) for n in taken if n.startswith(prefix + "-") and n.split("-")[-1].isdigit()]
    return f"{prefix}-{(max(nums) if nums else 0) + 1:02d}"


# --- selection and births (shared by the arena and the ghost worlds) -------------------------------------
def rank_key(row):
    f = row["fitness"]
    v = row["vs_index"]
    return (0 if f is not None else 1, -(f if f is not None else 0.0), -(v if v is not None else -1e9), row["name"])


def select_and_breed(ranking, members, taken, evaluation, seed_text):
    """ranking: eligible rows {name, fitness, vs_index}; members: name -> participant (needs dna, species).

    Returns (deaths [names, worst first], births [participant specs]) following rules/evolution.json.
    """
    ranked = sorted(ranking, key=rank_key)
    n = len(ranked)
    deaths_n = max(0, min(RULES["selection"]["deaths"], n - RULES["selection"]["min_survivors_among_eligible"]))
    if deaths_n == 0:
        return [], []
    dead = [r["name"] for r in ranked[n - deaths_n:]][::-1]   # worst first
    pool = [r["name"] for r in ranked[:n - deaths_n]][:RULES["selection"]["parents_pool"]]
    order = {name: i for i, name in enumerate(pool)}
    n_children = min(RULES["birth"]["children"], deaths_n)
    rng = rng_for(seed_text)
    taken = set(taken)
    births = []
    slots = [identity(members[d])["slot"] for d in dead]
    for k in range(n_children):
        two = sorted(rng.choice(len(pool), size=2, replace=False).tolist())
        a, b = pool[two[0]], pool[two[1]]
        if order[a] > order[b]:
            a, b = b, a
        pa, pb = members[a], members[b]
        dna = crossover_and_mutate(pa["dna"], pb["dna"], rng)
        sp = pa["species"]
        name = next_name(sp, taken)
        taken.add(name)
        births.append({"name": name, "type": pa["type"], "species": sp, "parents": [a, b], "dna": dna,
                       "generation": 1 + max(identity(pa)["generation"], identity(pb)["generation"]),
                       "cohort": evaluation, "slot": slots[k], "immigrant": False,
                       "gene_delta": gene_delta(dna, [pa["dna"], pb["dna"]])})
    for k in range(n_children, deaths_n):
        dna = immigrant_dna(rng)
        sp = nearest_species(dna["weights"])
        name = next_name(sp, taken)
        taken.add(name)
        any_type = members[dead[0]]["type"]
        births.append({"name": name, "type": any_type, "species": sp, "parents": None, "dna": dna,
                       "generation": 1, "cohort": evaluation, "slot": slots[k], "immigrant": True,
                       "gene_delta": None})
    return dead, births


def born_participant(spec, day, seed_id=None):
    p = new_participant({**spec, "seed_id": seed_id}, day)
    p["dna"] = spec["dna"]   # newborns carry every field of today's rules
    for f in ("generation", "cohort", "slot", "immigrant"):
        p[f] = spec[f]
    return p


# --- fitness --------------------------------------------------------------------------------------------------
def fitness(name, part, series, index_series):
    """Score since birth (arena.metrics) and return minus index; None when too short."""
    from .metrics import indicators
    if len(series) < 2:
        return None, None
    ind = indicators(name, series, index_series, part, None, series[-1][0][:4])
    return ind["score"], ind["vs_index"]


_VALUES_CACHE = {}


def value_history(archive, before):
    """{day: values} from every stored journal before `before` (journals never change once written)."""
    out = {}
    for d in archive.journal_days():
        if d >= before:
            break
        key = (str(archive.root), d)
        if key not in _VALUES_CACHE:
            _VALUES_CACHE[key] = archive.read_journal(d)["values"]
        out[d] = _VALUES_CACHE[key]
    return out


def series_of(name, born, history, today, today_values):
    s = [(d, v[name]) for d, v in history.items() if d >= born and name in v]
    s.append((today, today_values[name]))
    return s


# --- the hook in the night -----------------------------------------------------------------------------------
def apply(archive, state, day, values, decisions, view):
    """Evaluation night: deaths to the graveyard, births with fresh capital. Returns the journal record or None."""
    if day < RULES["effective_from"]:
        return None
    days = view.trading_days
    if not is_first_trading_day_of_month(day, days):
        return None
    agents = {n: p for n, p in state["participants"].items() if p["type"] == "agent"}
    eligible = sorted(n for n, p in agents.items() if is_eligible(p["born"], day, days))
    if not eligible:
        return None
    history = value_history(archive, day)
    idx = series_of(INDEX_NAME, "", history, day, values)
    rows = []
    for n in eligible:
        f, v = fitness(n, agents[n], series_of(n, agents[n]["born"], history, day, values), idx)
        rows.append({"name": n, "fitness": f, "vs_index": v})
    evaluation = state.get("evaluations", 0) + 1
    taken = list(state["participants"]) + list(state.get("graveyard", {}))
    dead, births = select_and_breed(rows, agents, taken, evaluation, f"evolution|{day}")
    ranked = sorted(rows, key=rank_key)
    place = {r["name"]: i + 1 for i, r in enumerate(ranked)}
    state["evaluations"] = evaluation
    if dead:
        graveyard = state.setdefault("graveyard", {})
        for n in dead:
            part = state["participants"].pop(n)
            part["pending"] = []
            r = next(x for x in rows if x["name"] == n)
            part["death"] = {"died": day, "evaluation": evaluation, "rank": place[n], "of": len(rows),
                             "fitness": r["fitness"], "vs_index": r["vs_index"], "value": values[n],
                             **identity(part)}
            graveyard[n] = part
        for b in births:
            spec = {k: v for k, v in b.items() if k != "gene_delta"}
            state["participants"][b["name"]] = born_participant(spec, day)
            values[b["name"]] = config.CAPITAL
            decisions[b["name"]] = {"events": [], "fills": [], "cancelled": []}
    return {
        "evaluation": evaluation,
        "rules_version": RULES["version"],
        "ranking": [{"name": r["name"], "rank": place[r["name"]], "fitness": r["fitness"],
                     "vs_index": r["vs_index"]} for r in ranked],
        "not_yet_eligible": sorted(n for n in agents if n not in eligible),
        "deaths": dead,
        "births": [{"name": b["name"], "species": b["species"], "parents": b["parents"], "slot": b["slot"],
                    "generation": b["generation"], "immigrant": b["immigrant"], "gene_delta": b["gene_delta"]}
                   for b in births],
    }


# --- null evolution: the same process on random agents (ghost worlds) ------------------------------------------
def _ghost_seed(w, name):
    return f"ghost-{w:02d}|{name}"


def _dna_updates(part, day):
    """Ghost founders gain later DNA fields on their effective date, as the arena's participants do."""
    src = next((p["dna"] for p in config.POPULATION["participants"] if p["name"] == part["name"]), None)
    if not src or part.get("cohort", 0):
        return
    for u in config.RULES.get("dna_updates", []):
        if u["effective_from"] <= day:
            for f in u["fields"]:
                if f not in part["dna"] and f in src:
                    part["dna"][f] = src[f]


def _fast_view(archive, day, cutoff):
    """The engine's View with dictionary lookups for opens and closes (same values, much faster for 200 ghosts)."""
    from .view import View

    class FastView(View):
        def _day(self, d):
            cache = self.__dict__.setdefault("_fast", {})
            if d not in cache:
                g = self._by_day.get(d)
                cache[d] = ({}, {}) if g is None else (g["open"].to_dict(), g["close"].to_dict())
            return cache[d]

        def open(self, ticker, d):
            v = self._day(d)[0].get(ticker)
            return None if v is None else float(v)

        def close(self, ticker, d):
            v = self._day(d)[1].get(ticker)
            return None if v is None else float(v)

    return FastView(archive, day, cutoff)


def simulate_null(archive, worlds=None):
    """Runs the ghost worlds over every stored night. Returns {world: {"evaluations": [...], "members": {...}}}."""
    from .agents import decide
    from .market import apply_events, fill_pending, sell, value
    worlds = RULES["null_evolution"]["worlds"] if worlds is None else worlds
    founders = [p for p in config.POPULATION["participants"] if p["type"] == "agent"]
    state = None
    hist = {w: {} for w in range(worlds)}
    index_hist = {}
    out = {w: {"evaluations": [], "graveyard": {}, "count": 0} for w in range(worlds)}
    for d in archive.journal_days():
        j = archive.read_journal(d)
        view = _fast_view(archive, d, j["inputs"]["cutoff"])
        rate = j["market"]["eurusd"]
        if state is None:
            state = {w: {p["name"]: new_participant({**p, "type": "monkey", "seed_id": _ghost_seed(w, p["name"])}, d)
                         for p in founders} for w in range(worlds)}
        else:
            events = view.events_on(d)
            delisted_today = [t for t, when in j["state"]["delisted"].items() if when == d]
            for w in range(worlds):
                for g in state[w].values():
                    g["days"] += 1
                    _dna_updates(g, d)
                    apply_events(g, events, rate)
                    fill_pending(g, view, d, rate)
                    for t in delisted_today:
                        g["pending"] = [o for o in g["pending"] if o["ticker"] != t]
                        price = view.last_close(t)
                        if t in g["positions"] and price:
                            sell(g, t, g["positions"][t]["shares"], price, rate, d)
        index_hist[d] = j["values"][INDEX_NAME]
        excluded = j["checks"]["excluded"]
        delisted = j["state"]["delisted"]
        z = pd.DataFrame(index=sorted(j["signals"]))
        ok = j["market"]["above_ma"]
        evaluation_day = (d >= RULES["effective_from"] and is_first_trading_day_of_month(d, view.trading_days))
        for w in range(worlds):
            vals = {n: value(g, view, d, rate) for n, g in state[w].items()}
            if evaluation_day:
                _evaluate_world(w, d, state[w], vals, hist[w], index_hist, view.trading_days, out[w])
            hist[w][d] = dict(vals)
            for n, g in state[w].items():
                g["pending"] = decide(g, d, view, rate, vals[n], z, None, excluded, delisted, ok)
    for w in range(worlds):
        out[w]["members"] = {n: _member_record(g) for n, g in {**out[w]["graveyard"], **(state or {}).get(w, {})}.items()}
        out[w]["final_values"] = hist[w][max(hist[w])] if hist[w] else {}
        del out[w]["graveyard"]
    return out


def _evaluate_world(w, d, members, vals, hist, index_hist, trading_days, out):
    eligible = sorted(n for n, g in members.items() if is_eligible(g["born"], d, trading_days))
    if not eligible:
        return
    idx = sorted((k, v) for k, v in index_hist.items() if k <= d)
    rows = []
    for n in eligible:
        s = [(k, v[n]) for k, v in sorted(hist.items()) if k >= members[n]["born"] and n in v] + [(d, vals[n])]
        f, v = fitness(n, members[n], s, idx)
        rows.append({"name": n, "fitness": f, "vs_index": v})
    out["count"] += 1
    taken = list(members) + list(out["graveyard"])
    dead, births = select_and_breed(rows, members, taken, out["count"], f"null-{w}|{d}")
    ranked = sorted(rows, key=rank_key)
    scored = [r["fitness"] for r in ranked if r["fitness"] is not None]
    out["evaluations"].append({
        "date": d, "evaluation": out["count"], "eligible": len(rows),
        "best": round(scored[0], 4) if scored else None,
        "top5_mean": round(float(np.mean(scored[:5])), 4) if scored else None,
        "median": round(float(np.median(scored)), 4) if scored else None,
        "deaths": dead, "births": [{"name": b["name"], "parents": b["parents"], "immigrant": b["immigrant"]} for b in births],
    })
    for n in dead:
        g = members.pop(n)
        g["death"] = {"died": d, "fitness": next(r["fitness"] for r in rows if r["name"] == n)}
        out["graveyard"][n] = g
    for b in births:
        spec = {k: v for k, v in b.items() if k != "gene_delta"}
        members[b["name"]] = born_participant(spec, d, seed_id=_ghost_seed(w, b["name"]))
        vals[b["name"]] = config.CAPITAL


def _member_record(p):
    ident = identity(p)
    rec = {"name": p["name"], "species": p["species"], "parents": p.get("parents"), "born": p["born"],
           "died": (p.get("death") or {}).get("died"), **ident,
           "dna": {g: p["dna"].get(g) for g in MANAGEMENT if g in p["dna"]}}
    return rec


# --- reports for the site (archive evolution/) ------------------------------------------------------------------
def _write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def evidence_label(cfg):
    if cfg.get("rehearsal"):
        return "technical rehearsal (price history only, today's universe, so survivorship-biased): never evidence"
    if cfg.get("mode") != "official":
        return "trial: results are wiped at the official start, never evidence"
    return "official"


def tree(archive):
    """Every agent ever born (alive and in the graveyard) with lineage, plus every evaluation."""
    days = archive.journal_days()
    if not days:
        return None
    last = archive.read_journal(days[-1])
    st = last["state"]
    evaluations = []
    for d in days:
        j = archive.read_journal(d)
        if "evolution" in j:
            evaluations.append({"date": d, **j["evolution"]})
    nodes = []
    everyone = {**{n: p for n, p in st["participants"].items() if p["type"] == "agent"}, **st.get("graveyard", {})}
    births = {b["name"]: (e["date"], b) for e in evaluations for b in e["births"]}
    for n, p in sorted(everyone.items(), key=lambda kv: (kv[1]["born"], identity(kv[1])["slot"] or 0, kv[0])):
        death = p.get("death")
        nodes.append({
            "name": n, "species": p["species"], **identity(p), "parents": p.get("parents"),
            "born": p["born"], "alive": death is None, "died": death["died"] if death else None,
            "death": None if not death else {k: death[k] for k in ("evaluation", "rank", "of", "fitness", "vs_index", "value")},
            "value": last["values"].get(n) if death is None else death["value"],
            "dna": p["dna"], "gene_delta": births[n][1]["gene_delta"] if n in births else None,
        })
    generations = {}
    for x in nodes:
        g = generations.setdefault(x["generation"], {"born": 0, "alive": 0})
        g["born"] += 1
        g["alive"] += x["alive"]
    return {"date": days[-1], "rules_version": RULES["version"], "evidence": evidence_label(archive.cfg),
            "evaluations": evaluations, "nodes": nodes,
            "generations": [{"generation": k, **v} for k, v in sorted(generations.items())]}


def null_report(archive, worlds=None):
    sim = simulate_null(archive, worlds)
    arena = {e["date"]: e for e in (tree(archive) or {"evaluations": []})["evaluations"]}
    comparison = []
    dates = sorted({e["date"] for w in sim.values() for e in w["evaluations"]})
    for d in dates:
        ghosts = [e for w in sim.values() for e in w["evaluations"] if e["date"] == d]
        a = arena.get(d)
        scores = [r["fitness"] for r in (a or {}).get("ranking", []) if r["fitness"] is not None]
        top5 = float(np.mean(scores[:5])) if scores else None
        g_top5 = [e["top5_mean"] for e in ghosts if e["top5_mean"] is not None]
        g_best = [e["best"] for e in ghosts if e["best"] is not None]
        comparison.append({
            "date": d,
            "agents_top5_mean": None if top5 is None else round(top5, 4),
            "agents_best": scores[0] if scores else None,
            "ghosts_top5_mean": [round(x, 4) for x in g_top5],
            "ghosts_best": g_best,
            "agents_top5_beats_worlds": None if top5 is None else round(float(np.mean([top5 > x for x in g_top5])), 4) if g_top5 else None,
        })
    return {"date": archive.journal_days()[-1] if archive.journal_days() else None,
            "rules_version": RULES["version"], "evidence": evidence_label(archive.cfg),
            "note": "Ghost worlds: the same evolution applied to random stock pickers. If the agents' winners are not clearly better than the ghosts' winners, selection is fitting noise.",
            "worlds": [{"world": w, **sim[w]} for w in sorted(sim)], "comparison": comparison}


def run(archive, worlds=None):
    """Writes evolution/tree.json and evolution/null.json; checks that past ghost evaluations replay identically."""
    out = archive.root / "evolution"
    t = tree(archive)
    if t is None:
        return {"date": None}
    _write(out / "tree.json", t)
    nr = null_report(archive, worlds)
    changed = []
    old_path = out / "null.json"
    if old_path.exists():
        old = json.loads(old_path.read_text(encoding="utf-8"))
        for ow, nw in zip(old.get("worlds", []), nr["worlds"]):
            for oe in ow["evaluations"]:
                ne = next((e for e in nw["evaluations"] if e["date"] == oe["date"]), None)
                if ne != oe:
                    changed.append(oe["date"])
    nr["replay_identical"] = not changed
    nr["changed_dates"] = sorted(set(changed))
    _write(old_path, nr)
    return {"date": t["date"], "evaluations": len(t["evaluations"]), "agents_ever": len(t["nodes"]),
            "replay_identical": nr["replay_identical"]}
