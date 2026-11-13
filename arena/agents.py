"""How each participant decides, every night (design 5.2 and 6.1).

Agents score companies with their DNA weights. Monkeys use the same management, but random scores.
Benchmarks buy on day one and never trade again.
Every justification is generated from the numbers that drove the decision.
"""
import hashlib

import numpy as np
import pandas as pd

from . import config
from .market import cents, position_value, round_shares
from .signals import drivers, score


def num(x, decimals=2):
    return f"{x:,.{decimals}f}"


def signed(x, decimals=2):
    return ("+" if x >= 0 else "−") + num(abs(x), decimals)


def ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def random_scores(seed_id, day, tickers):
    seed = int(hashlib.sha256(f"{seed_id}|{day}".encode()).hexdigest()[:16], 16)
    rng = np.random.default_rng(seed)
    return pd.Series(rng.standard_normal(len(tickers)).round(4), index=sorted(tickers)), seed


def decide(part, day, view, rate, value, z, raw, excluded, delisted, market_ok):
    kind = part["type"]
    if kind == "index":
        return _decide_index(part)
    if kind == "equal_weight":
        return _decide_equal_weight(part, excluded, delisted)
    return _decide_manager(part, day, view, rate, value, z, raw, excluded, delisted, market_ok)


def _decide_index(part):
    if part["days"] != 0:
        return []
    return [{"side": "buy", "ticker": config.INDEX_TOTAL, "eur": part["cash"], "slippage": False,
             "reason": {"text": "Benchmark: buys the S&P 500 with dividends on day one and never trades again."}}]


def _decide_equal_weight(part, excluded, delisted):
    if part["days"] != 0:
        return []
    targets = [t for t in config.universe_tickers() if t not in excluded and t not in delisted]
    eur = cents(int(part["cash"] / len(targets) * 100) / 100)
    return [{"side": "buy", "ticker": t, "eur": eur,
             "reason": {"text": f"Benchmark: equal weights in the {len(targets)} companies on day one; never trades again."}}
            for t in targets]


def _decide_manager(part, day, view, rate, V, z, raw, excluded, delisted, market_ok):
    dna = part["dna"]
    monkey = part["type"] == "monkey"
    pos = part["positions"]
    prices = {t: view.close(t, day) for t in pos}
    values = {t: position_value(p, prices[t], rate) if prices[t] else 0.0 for t, p in pos.items()}
    eligible = [t for t in z.index if t not in excluded and t not in delisted]
    if monkey:
        sc, seed = random_scores(part.get("seed_id") or part["name"], day, eligible)
    else:
        sc = score(z.loc[eligible], dna["weights"]) if eligible else pd.Series(dtype=float)
        seed = None
    ranking = sorted(eligible, key=lambda t: (-float(sc[t]), t))
    rank = {t: i + 1 for i, t in enumerate(ranking)}
    n_elig = len(ranking)
    orders = []
    sold = set()

    def info(t):
        d = {"score": float(sc[t]) if t in sc.index else None, "rank": rank.get(t), "of": n_elig}
        if not monkey and t in z.index:
            d["drivers"] = drivers(z, dna["weights"], t)
            for dr in d["drivers"]:
                b = raw.loc[t, dr["signal"]]
                dr["raw"] = None if pd.isna(b) else round(float(b), 4)
        if monkey:
            d["seed"] = str(seed)
        return d

    def explain(t):
        i = info(t)
        if i["score"] is None:
            return "", i
        base = f"Score {num(i['score'])} ({ordinal(i['rank'])} of {i['of']})."
        if monkey:
            return base + " Random pick (tonight's draw).", i
        parts = "; ".join(f"{config.SIGNAL_NAMES[d['signal']]} {signed(d['z'])}" for d in i["drivers"])
        return f"{base} Main drivers: {parts}.", i

    def sell(t, shares, everything, text, cause):
        e, i = explain(t)
        orders.append({"side": "sell", "ticker": t, "shares": round_shares(shares), "all": everything,
                       "reason": {"cause": cause, "text": f"{text} {e}".strip(), **i}})
        sold.add(t)

    def buy(t, eur, text, cause):
        e, i = explain(t)
        orders.append({"side": "buy", "ticker": t, "eur": cents(eur),
                       "reason": {"cause": cause, "text": f"{text} {e}".strip(), **i}})

    # 1. Stop loss (every day)
    stop = dna.get("stop_loss")
    if stop:
        for t, p in sorted(pos.items()):
            if prices[t] is None or t in excluded:
                continue
            avg = p["cost_eur"] / p["shares"]
            now = prices[t] / rate
            loss = now / avg - 1
            if loss <= -stop:
                sell(t, p["shares"], True,
                     f"Stop loss: {signed(loss * 100, 1)}% since purchase (limit −{num(stop * 100, 0)}%).",
                     "stop_loss")

    review = part["days"] % dna["review_days"] == 0
    wmax = min(dna["max_weight"], config.PORTFOLIO["max_weight_global"])
    band = config.PORTFOLIO["rebalance_band"]
    if review and n_elig:
        N = dna["n_holdings"]
        book = [t for t in pos if t not in sold]
        swaps = {}
        candidates = [t for t in ranking if t not in book and t not in sold]
        while len(book) < N and candidates:
            book.append(candidates.pop(0))
        while candidates:
            movable = [t for t in book if t in rank]
            if not movable:
                break
            worst = min(movable, key=lambda t: (float(sc[t]), t))
            best = candidates[0]
            if float(sc[best]) > float(sc[worst]) + dna["threshold"]:
                book.remove(worst)
                book.append(best)
                candidates.pop(0)
                swaps[worst] = best
            else:
                break
        f = 1.0 if market_ok or not dna.get("brake") else 1.0 - dna["brake"]
        weight = min(f / N, wmax)
        target = V * weight
        brake_txt = "" if f == 1.0 else f" Brake on: the market is below its 200-day average, so only {num(f * 100, 0)}% is invested."
        # Exits
        for t in sorted(pos):
            if t in sold or t in book:
                continue
            new = swaps.get(t)
            text = (f"Exit: fell to {ordinal(rank[t])}; replaced by {new} "
                    f"({num(float(sc[new]))} vs {num(float(sc[t]))}, a gap above the {num(dna['threshold'])} threshold)."
                    if new else "Exit: left the portfolio.")
            sell(t, pos[t]["shares"], True, text, "swap")
        # Adjustments and entries
        expected_cash = part["cash"]
        for o in orders:
            if o["side"] == "sell":
                p_ = pos[o["ticker"]]
                expected_cash += values.get(o["ticker"], 0.0) * (o["shares"] / p_["shares"]) * (1 - config.FX_COST - config.SLIPPAGE)
        buys = []
        for t in sorted(book, key=lambda t: (rank.get(t, 10**6), t)):
            if t in excluded or t not in rank and t not in pos:
                continue
            current = values.get(t, 0.0)
            diff = target - current
            if t not in pos:
                who = [k for k, v in swaps.items() if v == t]
                if monkey:
                    text = f"Entry by draw{', replacing ' + who[0] if who else ''}."
                else:
                    text = f"Entry: replaces {who[0]}." if who else "Entry: among the best."
                buys.append((t, target, text + brake_txt, "entry"))
            elif diff < -band * V and prices.get(t):
                shares = -diff / (prices[t] / rate)
                sell(t, shares, False,
                     f"Trims to the {num(weight * 100, 1)}% target weight (was {num(current / V * 100, 1)}%).{brake_txt}",
                     "rebalance")
                expected_cash += -diff * (1 - config.FX_COST - config.SLIPPAGE)
            elif diff > band * V:
                buys.append((t, diff, f"Tops up to the {num(weight * 100, 1)}% target weight (was {num(current / V * 100, 1)}%).", "rebalance"))
        total = sum(b[1] for b in buys)
        factor = 1.0 if total <= expected_cash or total == 0 else max(expected_cash, 0) / total
        for t, eur, text, cause in buys:
            eur = eur * factor
            if eur >= config.PORTFOLIO["min_order_eur"]:
                buy(t, eur, text, cause)
    else:
        # Outside review days: only the maximum weight is enforced
        for t, p in sorted(pos.items()):
            if t in sold or t in excluded or not prices[t]:
                continue
            if values[t] > (wmax + config.PORTFOLIO["weight_tolerance"]) * V:
                excess = values[t] - wmax * V
                sell(t, excess / (prices[t] / rate), False,
                     f"Maximum weight: was {num(values[t] / V * 100, 1)}%, limit {num(wmax * 100, 0)}%.",
                     "max_weight")
    return orders
