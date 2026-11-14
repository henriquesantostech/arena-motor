"""Append-only storage for the intelligence layer: immutable raw fetches + partitioned Parquet tables.

Rules (design v2, section 1):
  - every fetch is stored as fetched, gzip-compressed, named by its SHA-256 and never edited;
  - tables only grow: each run writes a new partition file; nothing is rewritten or deleted;
  - every row carries `recorded_at` (when we stored it); rows about the world also carry `published_at`
    (when the world could know it). A query "as known at T" filters both <= T.

DuckDB reads all partitions of a table in memory with one glob, so there is no database file in Git.
"""
import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Column contracts. Every column is text except the ones listed in NUMERIC. Timestamps are ISO 8601 UTC
# ("2026-11-13T21:05:00Z"); dates are "YYYY-MM-DD". Text keeps comparisons exact and replays bit-identical.
SCHEMAS = {
    "fetches": ["fetch_id", "source_id", "url", "fetched_at", "status", "bytes", "path", "content_type"],
    "entities": ["entity_id", "kind", "name", "ticker", "cik", "qid", "aliases", "recorded_at",
                 "source_id", "source_hash"],
    "facts": ["fact_id", "op", "subject_id", "predicate", "object_id", "value", "value_num",
              "valid_from", "valid_to", "published_at", "recorded_at", "source_id", "source_hash",
              "extractor", "extractor_version", "confidence"],
    "observations": ["series_id", "entity_id", "obs_date", "value", "vintage", "published_at",
                     "recorded_at", "source_id", "source_hash"],
    "documents": ["doc_id", "source_id", "kind", "url", "title", "published_at", "recorded_at",
                  "entity_ids", "lang", "text_sha", "raw_path", "extra"],
    "readings": ["doc_id", "reader", "reader_version", "model_sha", "label", "score", "output",
                 "recorded_at", "runtime"],
    "signals": ["date", "ticker", "signal_id", "value", "published_at", "recorded_at"],
    # computed after the fact from backfilled, PIT-trusted data: technical rehearsal only, never evidence
    "signals_rehearsal": ["date", "ticker", "signal_id", "value", "published_at", "recorded_at"],
    "alerts": ["alert_id", "kind", "person_id", "person_name", "role", "ticker", "action", "size_low",
               "size_high", "traded_on", "disclosed_at", "delay_days", "recorded_at", "source_id",
               "source_hash", "note"],
}
NUMERIC = {"bytes", "value_num", "value", "score", "confidence", "size_low", "size_high", "delay_days"}
# "value" is numeric in observations and signals, text in facts.
TEXT_VALUE_TABLES = {"facts"}


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(*parts) -> str:
    """Deterministic short id from its parts (same input = same id on every machine)."""
    return hashlib.sha256("\x1f".join("" if p is None else str(p) for p in parts).encode()).hexdigest()[:20]


def _arrow_type(table, col):
    if col in NUMERIC and not (col == "value" and table in TEXT_VALUE_TABLES):
        return pa.float64()
    return pa.string()


def arrow_schema(table):
    return pa.schema([(c, _arrow_type(table, c)) for c in SCHEMAS[table]])


class Store:
    """The intel/ part of the private archive."""

    def __init__(self, archive_root, run_id=None):
        self.root = Path(archive_root) / "intel"
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%H%M%S")
        self._pending = {}

    # --- raw archive -------------------------------------------------------------
    def put_raw(self, source_id, url, data: bytes, content_type="", status="ok", day=None):
        """Stores one fetch, returns (sha, relative path). Same bytes = same file (idempotent)."""
        h = sha256(data)
        day = day or utcnow()[:10]
        ext = _ext(content_type, url)
        rel = Path("raw") / source_id / day / f"{h[:16]}{ext}.gz"
        p = self.root / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            # mtime=0 keeps the gzip bytes identical for identical content
            with open(p, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as g:
                g.write(data)
        self.add("fetches", [{"fetch_id": h, "source_id": source_id, "url": url, "fetched_at": utcnow(),
                              "status": status, "bytes": float(len(data)), "path": rel.as_posix(),
                              "content_type": content_type}])
        return h, rel.as_posix()

    def get_raw(self, rel_path) -> bytes:
        with gzip.open(self.root / rel_path, "rb") as g:
            return g.read()

    # --- tables ------------------------------------------------------------------
    def add(self, table, rows):
        """Queues rows for the table; written by flush() as one new partition per table and run."""
        if not rows:
            return 0
        if isinstance(rows, pd.DataFrame):
            rows = rows.to_dict("records")
        self._pending.setdefault(table, []).extend(rows)
        return len(rows)

    def flush(self, day=None):
        day = day or utcnow()[:10]
        written = {}
        for table, rows in self._pending.items():
            if not rows:
                continue
            cols = SCHEMAS[table]
            df = pd.DataFrame(rows)
            for c in cols:
                if c not in df.columns:
                    df[c] = None
            df = df[cols]
            for c in cols:
                if _arrow_type(table, c) == pa.float64():
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                else:
                    df[c] = df[c].map(_to_text)
            df = df.drop_duplicates().sort_values(cols[:3], kind="mergesort").reset_index(drop=True)
            p = self.root / "tables" / table / day[:4] / f"{day}-{self.run_id}.parquet"
            n = 0
            while p.exists():   # never overwrite a partition
                n += 1
                p = p.with_name(f"{day}-{self.run_id}-{n}.parquet")
            p.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.Table.from_pandas(df, schema=arrow_schema(table), preserve_index=False), p,
                           compression="zstd")
            written[table] = len(df)
        self._pending = {}
        return written

    def glob(self, table):
        return (self.root / "tables" / table / "*" / "*.parquet").as_posix()

    def has(self, table):
        return any((self.root / "tables" / table).glob("*/*.parquet"))

    def read(self, table, where=None, params=None):
        """Reads a whole table (all partitions) with DuckDB; optional SQL WHERE clause."""
        if not self.has(table):
            return pd.DataFrame(columns=SCHEMAS[table])
        import duckdb
        q = f"SELECT * FROM read_parquet('{self.glob(table)}', union_by_name=true)"
        if where:
            q += f" WHERE {where}"
        with duckdb.connect() as con:
            return con.execute(q, params or []).df()

    def connect(self):
        """DuckDB in memory with one view per table (empty views for tables not written yet)."""
        import duckdb
        con = duckdb.connect()
        for t in SCHEMAS:
            if self.has(t):
                con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{self.glob(t)}', union_by_name=true)")
            else:
                cols = ", ".join(f"CAST(NULL AS {'DOUBLE' if _arrow_type(t, c) == pa.float64() else 'VARCHAR'}) AS {c}"
                                 for c in SCHEMAS[t])
                con.execute(f"CREATE VIEW {t} AS SELECT {cols} WHERE FALSE")
        return con

    # --- small state (cursors) -----------------------------------------------------
    def state(self, name, default=None):
        p = self.root / "state" / f"{name}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def set_state(self, name, value):
        p = self.root / "state" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                     newline="\n")


def _to_text(v):
    if v is None:
        return None
    if isinstance(v, float) and v != v:
        return None
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(v)


def _ext(content_type, url):
    ct = (content_type or "").lower()
    for k, e in (("json", ".json"), ("xml", ".xml"), ("rss", ".xml"), ("atom", ".xml"), ("csv", ".csv"),
                 ("html", ".html"), ("zip", ".zip"), ("pdf", ".pdf"), ("text/plain", ".txt")):
        if k in ct:
            return e
    m = re.search(r"\.(json|xml|csv|txt|zip|pdf|html?|xlsx?)(?:$|\?)", url.lower())
    return f".{m.group(1)}" if m else ".bin"
