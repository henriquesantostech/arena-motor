"""Data sources, each one a replaceable adapter behind a fixed interface.

The registry (rules/sources.json) records every source with its terms, licence and permitted use.
The rest of the engine only calls the functions below; to switch to a licensed provider, write a new
adapter that returns the same columns and point the registry at it. Nothing else changes.

Column contracts:
  prices  date, ticker, open, high, low, close, volume   (close not adjusted for dividends)
  events  date, ticker, type ('dividend' | 'split'), value
  fx      date, eurusd                                    (USD per 1 EUR)
  check   date, ticker, close
"""
import importlib
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .. import config

NEW_YORK = ZoneInfo("America/New_York")
USER_AGENT = {"User-Agent": "arena-of-agents/1.0 (paper-money experiment)"}


def registry():
    return config.SOURCES["sources"]


def _primary(role):
    for s in registry():
        if role in s.get("primary_for", []) or (role in s.get("role", []) and not s.get("primary_for")):
            mod = s["adapter"].replace("/", ".").removesuffix(".py")
            if mod.startswith("arena.sources."):
                return importlib.import_module(mod)
    raise RuntimeError(f"no source registered for {role}")


def last_closed_day(now=None):
    """Latest trading day whose close is final: from 18:00 New York time."""
    now = (now or datetime.now(tz=NEW_YORK)).astimezone(NEW_YORK)
    day = now.date()
    if now.time() < time(18, 0):
        day -= timedelta(days=1)
    return day.isoformat()


def prices_and_events(tickers, start, end_incl):
    return _primary("daily_prices").fetch(tickers, start, end_incl)


def fx_rates(start):
    return _primary("fx_rates").fetch(start)


def crosscheck_close(ticker, day):
    """Close of one company from the cross-check source, or None if unavailable."""
    return _primary("price_crosscheck").close(ticker, day)
