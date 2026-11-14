# Engine contracts

Stable interfaces between the engine and any extension (phase 2 intelligence, the site). An extension
plugs in through these contracts and never edits engine code. To change a contract, ask the engine owner;
changes are versioned here and logged in `rules/changes.md`.

## 1. Source registry — v1 (2026-11-13)

**Files.** `rules/sources.json` (engine sources) plus any number of extension files
`rules/sources_<area>.json` (e.g. `rules/sources_intel.json`). Each file is
`{"version", "date", "note", "sources": [ ... ]}`. Ids are unique across all files.
`arena.sources.registry()` returns every entry; `arena.sources.validate_registry()` returns the list of
problems (must be empty — enforced by the tests and by `python -m arena sources`).

**Required fields** (every entry): `id`, `provider`, `adapter` (path of the module, or how the data is
maintained), `data`, `terms`, `terms_url`, `license`, `use` (personal | any | …), `redistribution`,
`credentials` (`"none"` or where the key lives, never the key).

**Optional fields:** `role` (list), `primary_for` (list), `fallback`, `commercial_replacement`,
`pit_field`, `pit_trusted`, `rate_limit`, `terms_checked_on`, `env_key`, `budget_s`, `enabled`,
`contact_required`, `attribution`, `excluded_reason`. Other extra fields are allowed; tell the engine owner
so they get documented in `OPTIONAL_FIELDS` (`arena/sources/__init__.py`).

**Adapters.** One module per source, exposing `SOURCE_ID` equal to the registry id. The engine only calls
the roles it knows (`daily_prices`, `fx_rates`, `price_crosscheck`) through `arena.sources`; the column
contracts are in the docstring of `arena/sources/__init__.py`. Extension adapters (e.g.
`arena/intel/sources/*`) define their own roles and are called by their own pipeline.

## 2. Signal Lab input — v1 (2026-11-13)

The lab (`arena/lab.py`, `python -m arena lab`, also run at the end of every night) evaluates every
registered signal in **shadow mode**: it never changes a decision or any money.

**Shadow signal files (archive).** CSV, UTF-8, one or more files per night under
`intel/signals/shadow/YYYY/` (suggested name `YYYY-MM-DD[-run].csv`), append-only: never rewrite a file,
correct by writing a new row with a later `recorded_at`.

| column | meaning |
|---|---|
| `date` | the trading day D the value is "as of" (YYYY-MM-DD, New York trading calendar) |
| `ticker` | universe ticker as in `rules/universe.json` (e.g. `BRK.B`) |
| `signal_id` | `<area>.<name>`, lowercase, e.g. `intel.insider_cluster_buy`; `price.*` is reserved for the engine |
| `value` | float; **larger = more optimistic** for the stock |
| `published_at` | when the world could know the underlying information (ISO 8601 UTC, e.g. `2026-11-16T21:05:00Z`) |
| `recorded_at` | when we stored the value (ISO 8601 UTC) |

Phase 2 may also write the same columns as Parquet under `intel/tables/signals/YYYY/*.parquet`; the lab reads
them when pyarrow is installed (the nightly run installs `requirements-intel.txt` when present).

**Point-in-time rule.** A value counts for day D only if `published_at <= cutoff(D)` and
`recorded_at <= cutoff(D)`, where `cutoff(D)` is `inputs.cutoff` of the journal of night D (UTC).
For the same (`date`, `ticker`, `signal_id`), the row with the latest `recorded_at` before the cutoff wins.
Days without a journal are ignored.

**Pre-registration.** One file per signal, `rules/signals/<signal_id>.json`, written **before** its first
observation (`registered_on <= first date`, otherwise the pre-registration gate fails):

```json
{
 "signal_id": "intel.insider_cluster_buy",
 "family": "insider_purchases",
 "hypothesis": "plain-English statement of what should happen and why",
 "expected_sign": 1,
 "horizon_days": 21,
 "data": ["sec_edgar"],
 "admission_test": "gates_v1 (design v2 §8.3, arena/lab.py GATES)",
 "registered_on": "2026-11-20",
 "owner": "intel"
}
```

Phase 2 may instead list its pre-registrations in `rules/signals_shadow.json` (`{"signals": [{"id", "family",
"hypothesis", "expected_sign", "horizon_days", "data", "registered_on", ...}]}`); `id` is the signal id used in
the shadow table, `admission_test` defaults to gates_v1 and `owner` to intel.

`expected_sign` is 1 or -1; `horizon_days` is an integer in trading days (1–126); `data` lists registry ids.
Registration files are never edited after the first observation; a changed hypothesis is a new signal id.

**What the lab computes** (archive `lab/ic.csv`, `lab/report.json`):
- daily rank IC (Spearman) of the signal at D against the split-adjusted return from the open of D+1 to the
  open of D+1+h, multiplied by `expected_sign`;
- residual IC after a cross-sectional regression on `price.mom_12m`, `price.low_risk` and sector dummies;
- top-tercile spread over the universe (with a 50% decay haircut) versus top-tercile turnover × round-trip cost;
- gates v1 (design v2 §8.3): pre-registered; ≥ 250 observations; Newey–West t > 3 (lag = horizon);
  positive mean IC in ≥ 2 of 3 sub-periods; residual NW t > 2; haircut alpha > turnover cost.

Passing every gate sets `status: "passes_gates"`. That does **not** change any DNA: admitting a signal into
agents is a separate, logged rule change that applies only going forward.

**Python entry points** (stable): `arena.lab.run(archive) -> report dict`,
`arena.lab.load_signals(archive)`, `arena.lab.registrations()`, `arena.lab.validate_registration(r)`,
`arena.lab.newey_west_t(series, lag)`. `archive` is `arena.archive.Archive(<archive folder>)`.

## 3. Journal — v1 (2026-11-13)

One JSON package per night at `journal/YYYY/YYYY-MM-DD.json` in the archive. Top-level keys: `date`, `mode`,
`version`, `inputs` (incl. `cutoff`), `market`, `checks`, `signals`, `decisions`, `values`, `state`.
Read it only through `arena.archive.Archive.read_journal(day)`. Key-by-key description:
`arena/night.py` (`process_day`).
