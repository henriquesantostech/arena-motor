"""Entity registry and deterministic linking (design v2, section 3.5).

Entity ids are stable text keys:
  co:<TICKER>          company in the universe (ticker as frozen in rules/universe.json)
  cik:<CIK>            any other SEC filer (people, funds, companies outside the universe)
  wd:<QID>             Wikidata item (people, countries, parties, technologies)
  country:<ISO2>, ccy:<ISO3>, sector:<name>, series:<id>, member:<bioguide id>

Linking is a dictionary match on names, aliases and tickers. A reader (GLiNER2) proposes spans; this module
decides. Ambiguous cases may go to the LLM, whose choice is stored as a reading.
"""
import json
import re

from .. import config
from .store import stable_id, utcnow

# Words dropped when building name aliases ("Apple Inc." -> "Apple").
_SUFFIX = re.compile(r"[,.]?\s+(inc|incorporated|corp|corporation|co|company|plc|ltd|limited|llc|n\.?v|s\.?a|"
                     r"holdings?|group|the|class [abc])\.?$", re.I)
# Tickers that are also common words: only matched as $CASHTAG or in uppercase with a market context.
AMBIGUOUS_TICKERS = {"A", "ALL", "ARE", "BA", "C", "CAT", "COP", "DE", "DIS", "F", "GE", "GS", "HD", "KO", "LOW",
                     "MA", "MO", "MS", "NOW", "ON", "PM", "T", "TGT", "USB", "V", "IT", "SO", "DD", "BK", "MET"}
# Extra aliases a dictionary cannot infer (kept short and factual).
EXTRA_ALIASES = {
    "GOOGL": ["Google", "Alphabet"], "GOOG": ["Google", "Alphabet"], "META": ["Facebook", "Meta Platforms"],
    "BRK.B": ["Berkshire Hathaway", "Berkshire"], "JPM": ["JPMorgan", "J.P. Morgan", "JPMorgan Chase"],
    "XOM": ["Exxon", "ExxonMobil", "Exxon Mobil"], "KO": ["Coca-Cola"], "PG": ["Procter & Gamble", "P&G"],
    "UNH": ["UnitedHealth"], "LLY": ["Eli Lilly", "Lilly"], "MRK": ["Merck"], "BAC": ["Bank of America"],
    "WFC": ["Wells Fargo"], "GS": ["Goldman Sachs", "Goldman"], "MS": ["Morgan Stanley"], "TSLA": ["Tesla"],
    "NVDA": ["Nvidia"], "AMZN": ["Amazon"], "MSFT": ["Microsoft"], "AAPL": ["Apple"], "AVGO": ["Broadcom"],
}


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w&\-' ]", " ", s or "")).strip().lower()


def base_name(name):
    prev = None
    while prev != name:
        prev, name = name, _SUFFIX.sub("", name).strip()
    return name


def company_id(ticker):
    return f"co:{ticker}"


def universe_entities(cik_map=None, source_id="universe", source_hash=None):
    """Entity rows for the frozen universe (with CIK when the SEC map is known)."""
    rows = []
    now = utcnow()
    h = source_hash or stable_id(json.dumps(config.UNIVERSE, sort_keys=True))
    for c in config.UNIVERSE["companies"]:
        t = c["ticker"]
        aliases = sorted({c["name"], base_name(c["name"]), *EXTRA_ALIASES.get(t, [])})
        rows.append({"entity_id": company_id(t), "kind": "company", "name": c["name"], "ticker": t,
                     "cik": (cik_map or {}).get(t), "qid": None, "aliases": aliases, "recorded_at": now,
                     "source_id": source_id, "source_hash": h})
        rows.append({"entity_id": f"sector:{c['sector']}", "kind": "sector", "name": c["sector"], "ticker": None,
                     "cik": None, "qid": None, "aliases": [c["sector"]], "recorded_at": now,
                     "source_id": source_id, "source_hash": h})
    return rows


class Linker:
    """Deterministic dictionary linker over the universe (and any extra entities given)."""

    def __init__(self, entities_df=None):
        self.by_alias = {}
        self.ticker_to_id = {}
        companies = config.UNIVERSE["companies"]
        for c in companies:
            eid = company_id(c["ticker"])
            self.ticker_to_id[c["ticker"]] = eid
            for a in {c["name"], base_name(c["name"]), *EXTRA_ALIASES.get(c["ticker"], [])}:
                self._add(a, eid)
        if entities_df is not None and len(entities_df):
            for r in entities_df.itertuples():
                for a in json.loads(r.aliases or "[]") + [r.name]:
                    if a and len(a) >= 3:
                        self._add(a, r.entity_id)
        # longest aliases first so "Bank of America" wins over "America"
        self._pattern = re.compile(r"(?<![\w])(" + "|".join(
            re.escape(a) for a in sorted(self.by_alias, key=len, reverse=True)) + r")(?![\w])", re.I) \
            if self.by_alias else None

    def _add(self, alias, eid):
        a = norm(alias)
        if len(a) < 3:
            return
        self.by_alias.setdefault(a, set()).add(eid)

    def link_text(self, text):
        """Entity ids mentioned in a text: names/aliases, $CASHTAGS, and (TICKER) after an exchange name."""
        found = set()
        if not text:
            return []
        for m in re.finditer(r"\$([A-Z]{1,5}(?:\.[AB])?)\b", text):
            if m.group(1) in self.ticker_to_id:
                found.add(self.ticker_to_id[m.group(1)])
        for m in re.finditer(r"\((?:NYSE|NASDAQ|Nasdaq|NYSE American)\s*:\s*([A-Z.]{1,6})\)", text):
            if m.group(1) in self.ticker_to_id:
                found.add(self.ticker_to_id[m.group(1)])
        if self._pattern:
            for m in self._pattern.finditer(text):
                ids = self.by_alias.get(norm(m.group(1)), set())
                if len(ids) == 1:
                    found |= ids
        return sorted(found)

    def link_span(self, span):
        ids = self.by_alias.get(norm(span), set())
        if len(ids) == 1:
            return next(iter(ids))
        t = span.strip().lstrip("$").upper()
        if t in self.ticker_to_id and t not in AMBIGUOUS_TICKERS:
            return self.ticker_to_id[t]
        return None
