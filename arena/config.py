"""Rules and constants of the game, read from rules/*.json (public, in the engine repository)."""
import json
from pathlib import Path

ENGINE_VERSION = "1.0.0"

ENGINE_DIR = Path(__file__).resolve().parent.parent
RULES_DIR = ENGINE_DIR / "rules"
SITE_TEMPLATE_DIR = ENGINE_DIR / "site"


def _read(name):
    return json.loads((RULES_DIR / name).read_text(encoding="utf-8"))


RULES = _read("rules.json")
UNIVERSE = _read("universe.json")
POPULATION = _read("population.json")
SOURCES = _read("sources.json")

RULES_VERSION = RULES["version"]
CAPITAL = float(RULES["initial_capital_eur"])
FX_COST = RULES["costs"]["fx"]
SLIPPAGE = RULES["costs"]["slippage"]
WITHHOLDING = RULES["costs"]["dividend_withholding"]
PORTFOLIO = RULES["portfolio"]
DATA = RULES["data"]
METRICS = RULES["metrics"]
SIGNALS = POPULATION["signals"]
PRICE_SIGNALS = SIGNALS[:8]   # the ones computed in phase 1

# Indices (benchmark and market "brake" only)
INDEX_PRICE = "^GSPC"      # S&P 500 (price)
INDEX_TOTAL = "^SP500TR"   # S&P 500 with dividends reinvested
INDICES = [INDEX_PRICE, INDEX_TOTAL]


def universe_tickers():
    return [c["ticker"] for c in UNIVERSE["companies"]]


def yahoo_symbol(ticker):
    return ticker if ticker.startswith("^") else ticker.replace(".", "-")


NAMES = {c["ticker"]: c["name"] for c in UNIVERSE["companies"]}

SIGNAL_NAMES = {
    "mom_1m": "1-month trend",
    "mom_3m": "3-month trend",
    "mom_6m": "6-month trend",
    "mom_12m": "12-month trend",
    "rev_1w": "last week's drop",
    "rev_1m": "last month's drop",
    "low_risk": "low risk",
    "near_high": "near the 1-year high",
    "news": "news",
    "value": "value",
    "quality": "quality",
}
