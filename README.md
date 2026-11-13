# Arena of Agents — engine

A **paper-money** experiment: 20 autonomous agents, 10 "monkeys" that pick at random and 2 benchmarks
compete on the real S&P 100, each starting with €100,000 of fictitious money. Everything is transparent:
every decision carries its justification, and any night can be replayed with exactly the same result.

**Nothing here is investment advice. There is no connection to any broker and no real orders.**

> **Licence: all rights reserved.** The code is public for transparency only. It may not be used,
> copied or redistributed without written permission. See [LICENSE](LICENSE).

This public repository holds only the code and the rules of the game. Raw data from the sources and the
results live in a private archive, because the sources' terms do not allow republishing them.

The design of the whole project is in [docs/design-v2.md](docs/design-v2.md).

## How a night works

It runs on its own on GitHub, Tuesday to Saturday at 02:00 UTC, after the New York close:

1. **Fetch** daily prices and corporate actions (dividends, splits), the ECB EUR/USD rate, and a Tiingo
   sample for cross-checking. Data is only ever appended to the archive, never rewritten.
2. **Check**: companies with missing data or suspicious price jumps sit out that night.
3. **Fill** at today's open the orders decided last night, with costs (0.15% FX + 0.05% slippage).
   Dividends (15% withholding) and splits are applied first.
4. **Value** every portfolio at the close.
5. **Signals**: trend (1, 3, 6 and 12 months), mean reversion (week, month) and risk (volatility, distance to the 1-year high).
6. **Decide**: each agent scores the companies with its DNA weights and decides what to buy and sell tomorrow.
7. **Journal**: one package per night with input fingerprints, signals, decisions, justifications and portfolios.
8. **Site**: built from the journal.

## Rules and principles

- Decisions use only what was known at the close; fills happen at the next open.
- Costs are always included. Long only, no leverage, at most 20% in one company. Fractional shares.
- Benchmarks: S&P 500 total return in euros, and equal weights in the 100 companies, never rebalanced.
- Monkeys copy an agent's management but pick at random, to show how much luck alone achieves.
- Rule changes are logged in `rules/changes.md` and only apply from then on.

## Data sources

Each source is a replaceable adapter in `arena/sources/` behind a fixed interface. `rules/sources.json`
records, for every source, its role, terms, licence, permitted use and the commercial replacement.
Current use is personal and non-commercial. List them with `python -m arena sources`.

| Source | Role | Use |
|---|---|---|
| Yahoo Finance (yfinance) | daily prices, dividends, splits | personal |
| European Central Bank | EUR/USD reference rate | public (attribution) |
| Tiingo (free account) | nightly cross-check of closes | personal |
| Public S&P 100 list | universe, frozen with a date | personal |

## Layout

| Path | What it does |
|---|---|
| `rules/rules.json` | costs, limits and metrics (the rules of the game) |
| `rules/universe.json` | the 101 S&P 100 stocks, frozen with a date |
| `rules/population.json` | the DNA of the 20 agents, the 10 monkeys and the 2 benchmarks |
| `rules/sources.json` | data source registry (terms, licences, permitted use) |
| `rules/changes.md` | every rule change, with date and reason |
| `arena/sources/` | source adapters (Yahoo, ECB, Tiingo) behind one interface |
| `arena/archive.py` | reading and appending to the private archive; fingerprints |
| `arena/view.py` | what was known at the end of each day (nothing from the future gets in) |
| `arena/checks.py` | data checks |
| `arena/signals.py` | price signals |
| `arena/market.py` | the referee: fills, costs, dividends, splits |
| `arena/agents.py` | how each participant decides and justifies |
| `arena/night.py` | the whole night; replaying a night |
| `arena/metrics.py` | indicators and ranking score |
| `arena/audit.py` | independent audit of a participant's accounts (CSV for Excel) |
| `arena/site.py`, `site/` | the website |
| `tests/` | tests on made-up data |
| `.github/workflows/` | nightly run and tests |

## Commands (from the engine folder)

```
.venv\Scripts\python.exe -m arena night    --archive ..\arena-arquivo
.venv\Scripts\python.exe -m arena replay   --archive ..\arena-arquivo --date 2026-11-20
.venv\Scripts\python.exe -m arena audit    --archive ..\arena-arquivo --participant Arrow-01
.venv\Scripts\python.exe -m arena sources
.venv\Scripts\python.exe -m pytest -q
```

To see the site with the latest night: `.\open_site.ps1` (updates the archive and opens the site).

## Setup

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`phase0/` keeps the very first program (a price chart); it also needs `matplotlib`.
