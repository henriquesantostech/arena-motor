"""The referee: fills orders at the open and applies costs, dividends, splits and delistings.

The account is in euros. Each buy converts euros to dollars and each sell converts dollars to euros:
  0.15% FX cost on the converted amount + 0.05% slippage on the price.
"""
import math

from . import config

DECIMALS = config.PORTFOLIO["share_decimals"]


def cents(x):
    return round(x + 0.0, 2)


def round_shares(x):
    return round(x + 0.0, DECIMALS)


def floor_shares(x):
    f = 10 ** DECIMALS
    return math.floor(x * f + 1e-9) / f


def dna_at(dna, day):
    """The DNA as the rules stood on `day`: fields of later DNA updates are left out."""
    if dna is None:
        return None
    later = {f for u in config.RULES.get("dna_updates", []) if u["effective_from"] > day for f in u["fields"]}
    return {k: v for k, v in dna.items() if k not in later}


def new_participant(p, day):
    return {
        "name": p["name"], "type": p["type"], "species": p["species"],
        "parents": p.get("parents"), "copies_management_of": p.get("copies_management_of"),
        "seed_id": p.get("seed_id"),
        "dna": dna_at(p["dna"], day), "born": day, "days": 0,
        "cash": config.CAPITAL, "positions": {}, "pending": [],
        "totals": {"costs": 0.0, "dividends": 0.0, "buys_eur": 0.0, "sells_eur": 0.0,
                   "closed": 0, "winners": 0, "realized_gains": {}},
    }


def _cost(part, eur):
    part["totals"]["costs"] = cents(part["totals"]["costs"] + eur)


def buy(part, ticker, eur, price_usd, rate, day, slippage=True):
    """Spends `eur` euros. Returns the fill record."""
    eur = cents(min(eur, part["cash"]))
    if eur < config.PORTFOLIO["min_order_eur"]:
        return None
    fx_cost = eur * config.FX_COST
    usd = (eur - fx_cost) * rate
    eff_price = price_usd * (1 + config.SLIPPAGE) if slippage else price_usd
    shares = floor_shares(usd / eff_price)
    if shares <= 0:
        return None
    slip_cost = shares * (eff_price - price_usd) / rate
    part["cash"] = cents(part["cash"] - eur)
    pos = part["positions"].setdefault(ticker, {"shares": 0.0, "cost_eur": 0.0, "since": day})
    pos["shares"] = round_shares(pos["shares"] + shares)
    pos["cost_eur"] = cents(pos["cost_eur"] + eur)
    _cost(part, fx_cost + slip_cost)
    part["totals"]["buys_eur"] = cents(part["totals"]["buys_eur"] + eur)
    return {"side": "buy", "ticker": ticker, "shares": shares, "price_usd": price_usd,
            "effective_price_usd": round(eff_price, 6), "eurusd": rate, "eur": eur,
            "fx_cost_eur": cents(fx_cost), "slippage_cost_eur": cents(slip_cost)}


def sell(part, ticker, shares, price_usd, rate, day, slippage=True):
    pos = part["positions"].get(ticker)
    if not pos:
        return None
    shares = round_shares(min(shares, pos["shares"]))
    if shares <= 0:
        return None
    eff_price = price_usd * (1 - config.SLIPPAGE) if slippage else price_usd
    usd = shares * eff_price
    gross_eur = usd / rate
    fx_cost = gross_eur * config.FX_COST
    eur = cents(gross_eur - fx_cost)
    slip_cost = shares * (price_usd - eff_price) / rate
    fraction = shares / pos["shares"]
    cost_out = cents(pos["cost_eur"] * fraction)
    gain = cents(eur - cost_out)
    part["cash"] = cents(part["cash"] + eur)
    _cost(part, fx_cost + slip_cost)
    t = part["totals"]
    t["sells_eur"] = cents(t["sells_eur"] + eur)
    year = day[:4]
    t["realized_gains"][year] = cents(t["realized_gains"].get(year, 0.0) + gain)
    left = round_shares(pos["shares"] - shares)
    if left <= 0 or fraction > 0.999999:
        t["closed"] += 1
        if gain + pos.get("partial_gain", 0.0) > 0:   # whole round trip, including earlier partial sells
            t["winners"] += 1
        del part["positions"][ticker]
    else:
        pos["shares"] = left
        pos["cost_eur"] = cents(pos["cost_eur"] - cost_out)
        pos["partial_gain"] = cents(pos.get("partial_gain", 0.0) + gain)
    return {"side": "sell", "ticker": ticker, "shares": shares, "price_usd": price_usd,
            "effective_price_usd": round(eff_price, 6), "eurusd": rate, "eur": eur,
            "fx_cost_eur": cents(fx_cost), "slippage_cost_eur": cents(slip_cost),
            "gain_eur": gain}


def apply_events(part, events, rate):
    """Dividends and splits with ex-date today, on the holdings before today's orders."""
    done = []
    for _, ev in events.iterrows():
        t = ev["ticker"]
        pos = part["positions"].get(t)
        if not pos:
            continue
        v = float(ev["value"])
        if ev["type"] == "split":
            before = pos["shares"]
            pos["shares"] = round_shares(before * v)
            done.append({"type": "split", "ticker": t, "ratio": v, "shares_before": before,
                         "shares_after": pos["shares"]})
        elif ev["type"] == "dividend":
            gross_usd = pos["shares"] * v
            net_usd = gross_usd * (1 - config.WITHHOLDING)
            gross_eur = net_usd / rate
            fx_cost = gross_eur * config.FX_COST
            eur = cents(gross_eur - fx_cost)
            part["cash"] = cents(part["cash"] + eur)
            part["totals"]["dividends"] = cents(part["totals"]["dividends"] + eur)
            _cost(part, fx_cost)
            done.append({"type": "dividend", "ticker": t, "per_share_usd": v, "shares": pos["shares"],
                         "withholding_usd": round(gross_usd - net_usd, 4), "eurusd": rate, "eur": eur})
    return done


def fill_pending(part, view, day, rate):
    """Orders decided last night, filled at today's open. Sells first, then buys."""
    fills, cancelled = [], []
    pending = part["pending"]
    part["pending"] = []
    for o in [o for o in pending if o["side"] == "sell"]:
        price = view.open(o["ticker"], day)
        if price is None:
            cancelled.append({**o, "cause": "no opening price"})
            continue
        pos = part["positions"].get(o["ticker"])
        if not pos:
            cancelled.append({**o, "cause": "no position"})
            continue
        shares = pos["shares"] if o.get("all") else o["shares"]
        r = sell(part, o["ticker"], shares, price, rate, day)
        if r:
            r["reason"] = o["reason"]
            fills.append(r)
    buys = [o for o in pending if o["side"] == "buy"]
    valid = []
    for o in buys:
        price = view.open(o["ticker"], day)
        if price is None:
            cancelled.append({**o, "cause": "no opening price"})
        else:
            valid.append((o, price))
    total = sum(o["eur"] for o, _ in valid)
    factor = 1.0 if total <= part["cash"] or total == 0 else part["cash"] / total
    for o, price in valid:
        eur = math.floor(o["eur"] * factor * 100) / 100
        r = buy(part, o["ticker"], eur, price, rate, day, slippage=o.get("slippage", True))
        if r:
            if factor < 1:
                r["scaled"] = round(factor, 6)
            r["reason"] = o["reason"]
            fills.append(r)
    return fills, cancelled


def value(part, view, day, rate):
    """Portfolio value at the close of D (or the last known close)."""
    total = part["cash"]
    for t, pos in part["positions"].items():
        price = view.close(t, day)
        if price is None:
            price = view.last_close(t) or 0.0
        total += pos["shares"] * price / rate
    return cents(total)


def position_value(pos, price_usd, rate):
    return pos["shares"] * price_usd / rate
