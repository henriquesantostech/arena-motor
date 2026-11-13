"""Independent audit of one participant's accounts (for the "3 agents match by hand" criterion).

It does not use the engine code: it reads only the raw files (prices, events, FX) and the journal fills,
redoes every calculation from the rules in rules.json, and compares with the value the engine stored.
It writes a CSV (opens in Excel) with every calculation step.
"""
import csv
import json
import math
from pathlib import Path

RULES = json.loads((Path(__file__).resolve().parent.parent / "rules" / "rules.json").read_text(encoding="utf-8"))
FX = RULES["costs"]["fx"]
SLIP = RULES["costs"]["slippage"]
WHT = RULES["costs"]["dividend_withholding"]
DEC = RULES["portfolio"]["share_decimals"]


def _read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def audit(archive, name, out=None):
    root = Path(archive.root)
    prices = {}
    for r in _read_csv(root / "raw" / "prices.csv"):
        prices[(r["date"], r["ticker"])] = (float(r["open"]), float(r["close"]))
    events = {}
    for r in _read_csv(root / "raw" / "events.csv"):
        events.setdefault(r["date"], []).append((r["ticker"], r["type"], float(r["value"])))
    fx = sorted((r["date"], float(r["eurusd"])) for r in _read_csv(root / "raw" / "fx.csv"))

    def rate(d):
        t = None
        for date, v in fx:
            if date > d:
                break
            t = v
        return t

    last_close = {}
    days = sorted(p.stem for p in (root / "journal").glob("*/*.json"))
    cash = None
    shares = {}
    rows = []
    max_diff = 0.0
    for d in days:
        j = json.loads((root / "journal" / d[:4] / f"{d}.json").read_text(encoding="utf-8"))
        if name not in j["values"]:
            continue
        r_ = rate(d)
        if cash is None:
            cash = float(RULES["initial_capital_eur"])
            rows.append([d, "birth", "", "", "", "", "", "", round(cash, 2), ""])
        else:
            # dividends and splits with ex-date today
            for t, kind, v in events.get(d, []):
                if t not in shares:
                    continue
                if kind == "split":
                    shares[t] = round(shares[t] * v, DEC)
                    rows.append([d, "split", t, shares[t], v, "", "", "", round(cash, 2), "shares × ratio"])
                else:
                    eur = round(shares[t] * v * (1 - WHT) / r_ * (1 - FX), 2)
                    cash = round(cash + eur, 2)
                    rows.append([d, "dividend", t, shares[t], v, r_, "", eur, round(cash, 2),
                                 "shares × dividend × 0.85 ÷ FX × (1 − 0.15%)"])
            # fills at the open (the journal says what; here we redo how much)
            for ex in j["decisions"][name]["fills"]:
                t = ex["ticker"]
                cause = ex.get("reason", {}).get("cause")
                open_ = prices[(d, t)][0] if cause != "delisting" else ex["price_usd"]
                slip = 0.0 if ex.get("effective_price_usd") == ex["price_usd"] else SLIP
                if ex["side"] == "buy":
                    eur = ex["eur"]
                    n = math.floor((eur * (1 - FX) * r_) / (open_ * (1 + slip)) * 10**DEC + 1e-9) / 10**DEC
                    shares[t] = round(shares.get(t, 0.0) + n, DEC)
                    cash = round(cash - eur, 2)
                    note = "shares = € × (1 − 0.15%) × FX ÷ (open × 1.0005)"
                    max_diff = max(max_diff, abs(n - ex["shares"]))
                else:
                    n = ex["shares"]
                    eur = round(n * open_ * (1 - slip) / r_ * (1 - FX), 2)
                    shares[t] = round(shares.get(t, 0.0) - n, DEC)
                    if shares[t] <= 1e-9:
                        del shares[t]
                    cash = round(cash + eur, 2)
                    note = "€ = shares × open × 0.9995 ÷ FX × (1 − 0.15%)"
                rows.append([d, ex["side"], t, n, open_, r_, "", eur, round(cash, 2), note])
                max_diff = max(max_diff, abs(eur - ex["eur"]))
        # valuation at the close
        val = cash
        for t, n in shares.items():
            pc = prices.get((d, t))
            if pc:
                last_close[t] = pc[1]
            c = last_close.get(t) or _last(prices, t, d)
            val += n * c / r_
        val = round(val, 2)
        engine = j["values"][name]
        diff = round(val - engine, 2)
        max_diff = max(max_diff, abs(diff))
        rows.append([d, "close", "", "", "", r_, engine, val, round(cash, 2),
                     "value = cash + Σ shares × close ÷ FX" + ("" if abs(diff) <= 0.05 else f"  <<< DIFFERENCE {diff}")])
    out = Path(out) if out else root / "audits" / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "what", "company", "shares", "price/dividend/ratio (USD)", "EUR/USD",
                    "engine value (€)", "independent calculation (€)", "cash (€)", "how it is calculated"])
        w.writerows(rows)
    ok = max_diff <= 0.05
    return f"{name}: {'matches' if ok else 'DOES NOT match'} (largest difference €{max_diff:.2f}) -> {out}"


def _last(prices, t, d):
    dates = sorted(date for (date, tk) in prices if tk == t and date <= d)
    return prices[(dates[-1], t)][1] if dates else 0.0
