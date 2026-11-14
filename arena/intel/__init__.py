"""Phase 2 intelligence layer: World Knowledge Base, source adapters, AI readers, people module, shadow signals.

Everything here is additive to the phase 1 engine. Nothing in this package changes an agent's decision:
every new signal is written in shadow mode and only the Signal Lab can admit it (design v2, section 8.3).

Archive layout (private repository, under intel/):
  raw/<source>/<YYYY-MM-DD>/<sha>.<ext>.gz   every fetch as fetched, gzip, named by its SHA-256 (immutable)
  tables/<table>/<YYYY>/<YYYY-MM-DD>-<run>.parquet  append-only partitions of the knowledge base tables
  brief/<YYYY>/<YYYY-MM-DD>.json            Daily World Brief (never regenerated)
  lab/                                      shadow IC reports
  state/                                    small cursors (last item seen per source)
"""
INTEL_VERSION = "0.2.0"
