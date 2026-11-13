"""What was known at the end of day D. Nothing after D gets in (golden rule 2)."""
import pandas as pd

from . import config
from .archive import fingerprint

WINDOW_CALENDAR_DAYS = 420   # enough for 12 months of trading plus margin


class View:
    def __init__(self, archive, day, cutoff):
        """cutoff: only rows fetched up to this date and time (so a replayed night sees the same data)."""
        self.day = day
        start = (pd.Timestamp(day) - pd.Timedelta(days=WINDOW_CALENDAR_DAYS)).date().isoformat()

        def upto(name):
            df = archive.read(name)
            return df[df["fetched_at"] <= cutoff]

        p = upto("prices")
        self.prices = p[(p["date"] <= day) & (p["date"] >= start)].reset_index(drop=True)
        e = upto("events")
        self.events = e[e["date"] <= day].reset_index(drop=True)
        f = upto("fx")
        self.fx = f[(f["date"] <= day) & (f["date"] >= start)].reset_index(drop=True)
        t = upto("tiingo")
        self.tiingo = t[t["date"] == day].reset_index(drop=True)

        idx = self.prices[self.prices["ticker"] == config.INDEX_PRICE]
        self.trading_days = sorted(idx["date"].unique().tolist())
        self._by_day = {d: g.set_index("ticker") for d, g in self.prices.groupby("date")}
        self._adj_close = None

    # --- input fingerprints ----------------------------------------------------
    def fingerprints(self):
        return {
            "prices": fingerprint(self.prices),
            "events": fingerprint(self.events),
            "fx": fingerprint(self.fx),
            "tiingo": fingerprint(self.tiingo),
        }

    # --- lookups -----------------------------------------------------------------
    def is_trading_day(self, d):
        return d in self._by_day and config.INDEX_PRICE in self._by_day[d].index

    def row(self, ticker, d):
        g = self._by_day.get(d)
        if g is None or ticker not in g.index:
            return None
        return g.loc[ticker]

    def open(self, ticker, d):
        r = self.row(ticker, d)
        return None if r is None else float(r["open"])

    def close(self, ticker, d):
        r = self.row(ticker, d)
        return None if r is None else float(r["close"])

    def last_close(self, ticker):
        """Last known close up to D (to value a position when the day is missing)."""
        s = self.prices[self.prices["ticker"] == ticker]
        return None if s.empty else float(s["close"].iloc[-1])

    def rate(self, d=None):
        d = d or self.day
        f = self.fx[self.fx["date"] <= d]
        if f.empty:
            raise RuntimeError(f"no ECB exchange rate up to {d}")
        return float(f["eurusd"].iloc[-1])

    def events_on(self, d):
        return self.events[self.events["date"] == d]

    def tickers_on(self, d):
        g = self._by_day.get(d)
        return set() if g is None else set(g.index)

    def adjusted_close(self):
        """Days × companies table of closes adjusted for splits (signals and checks only).

        A row fetched before a split was not yet adjusted by the source: divide it by the ratio.
        """
        if self._adj_close is not None:
            return self._adj_close
        p = self.prices[["date", "ticker", "close", "fetched_at"]].copy()
        splits = self.events[self.events["type"] == "split"]
        for _, s in splits.iterrows():
            m = (p["ticker"] == s["ticker"]) & (p["date"] < s["date"]) & (p["fetched_at"] < s["date"])
            p.loc[m, "close"] = p.loc[m, "close"] / float(s["value"])
        tab = p.pivot(index="date", columns="ticker", values="close").sort_index()
        tab = tab.loc[[d for d in tab.index if d in set(self.trading_days)]]
        self._adj_close = tab
        return tab
