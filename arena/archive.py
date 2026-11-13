"""The private archive: raw data (append-only, never rewritten), journal and state.

Layout:
  arena.json                     configuration of this arena (mode, day zero)
  raw/prices.csv                 date,ticker,open,high,low,close,volume,fetched_at
  raw/events.csv                 date,ticker,type,value,fetched_at   (dividends and splits)
  raw/fx.csv                     date,eurusd,fetched_at              (ECB)
  raw/tiingo.csv                 date,ticker,close,fetched_at        (cross-check sample)
  journal/YYYY/YYYY-MM-DD.json   one package per night
  journal/log.csv                when each night ran and how it went
  audits/                        independent audits (CSV)
  site/                          private site
"""
import hashlib
import json
from pathlib import Path

import pandas as pd

COLUMNS = {
    "prices": ["date", "ticker", "open", "high", "low", "close", "volume", "fetched_at"],
    "events": ["date", "ticker", "type", "value", "fetched_at"],
    "fx": ["date", "eurusd", "fetched_at"],
    "tiingo": ["date", "ticker", "close", "fetched_at"],
}
KEYS = {
    "prices": ["date", "ticker"],
    "events": ["date", "ticker", "type"],
    "fx": ["date"],
    "tiingo": ["date", "ticker"],
}
TEXT = {"date": str, "ticker": str, "type": str, "fetched_at": str}


class Archive:
    def __init__(self, root):
        self.root = Path(root)
        self._cache = {}

    # --- configuration ---------------------------------------------------------
    @property
    def cfg(self):
        return json.loads((self.root / "arena.json").read_text(encoding="utf-8"))

    def write_cfg(self, cfg):
        self.root.mkdir(parents=True, exist_ok=True)
        write_json(self.root / "arena.json", cfg)

    # --- raw data ----------------------------------------------------------------
    def path(self, name):
        return self.root / "raw" / f"{name}.csv"

    def read(self, name):
        if name in self._cache:
            return self._cache[name]
        p = self.path(name)
        if p.exists():
            df = pd.read_csv(p, dtype=TEXT, keep_default_na=False, na_values=[""])
        else:
            df = pd.DataFrame(columns=COLUMNS[name])
        self._cache[name] = df
        return df

    def append(self, name, new, fetched_at):
        """Adds only rows whose key is not there yet. Never changes existing rows."""
        if new is None or len(new) == 0:
            return 0
        current = self.read(name)
        new = new.copy()
        new["fetched_at"] = fetched_at
        new = new[COLUMNS[name]]
        key = KEYS[name]
        seen = set(map(tuple, current[key].astype(str).values.tolist())) if len(current) else set()
        mask = [tuple(map(str, r)) not in seen for r in new[key].values.tolist()]
        new = new[mask].drop_duplicates(subset=key)
        if not len(new):
            return 0
        allrows = pd.concat([current, new], ignore_index=True) if len(current) else new
        allrows = allrows.sort_values(key, kind="mergesort").reset_index(drop=True)
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        allrows.to_csv(p, index=False, lineterminator="\n")
        self._cache.pop(name, None)
        return len(new)

    # --- journal ---------------------------------------------------------------
    def journal_path(self, day):
        return self.root / "journal" / day[:4] / f"{day}.json"

    def read_journal(self, day):
        p = self.journal_path(day)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def journal_days(self):
        return sorted(p.stem for p in (self.root / "journal").glob("*/*.json"))

    def write_journal(self, day, package):
        write_json(self.journal_path(day), package)

    def log(self, line):
        p = self.root / "journal" / "log.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        new = not p.exists()
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            if new:
                f.write("ran_at,action,days,result\n")
            f.write(line + "\n")


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(obj, indent=1) + "\n", encoding="utf-8", newline="\n")


def canonical_json(obj, indent=None):
    return json.dumps(obj, ensure_ascii=False, indent=indent, sort_keys=False, allow_nan=False)


def fingerprint(df_or_obj):
    """SHA-256 of the content. If a single number changes, the fingerprint changes."""
    if isinstance(df_or_obj, pd.DataFrame):
        text = df_or_obj.to_csv(index=False, lineterminator="\n", float_format="%.6f")
    else:
        text = canonical_json(df_or_obj)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
