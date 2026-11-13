# Agent Arena — Design v2

- **Version:** 2.0 (2026-11-13). Supersedes v1.1 where they differ; v1.1 (an earlier internal document) stays as history.
- **Scope:** the intelligence layer (world knowledge, sources, signals, AI readers), the rigour framework, product readiness, and UX principles. Market simulation, costs and population rules from v1.1 still apply unless changed here.
- **Status:** proposal, applied phase by phase.
- **Disclaimer:** fictitious money only. Nothing here is investment advice; the system never connects to a broker.

## Contents

0. Executive summary
1. Rigour charter
2. Architecture
3. World Knowledge Base
4. Source catalogue
5. Signal families and what the evidence says
6. Politicians and insiders module
7. Agents v2
8. Evaluation: how we avoid fooling ourselves
9. Zero-cost AI stack
10. Infrastructure
11. Product readiness
12. UX principles
13. Roadmap
14. Risks
15. Owner decisions
- Appendix: references

---

## 0. Executive summary

**Goal.** Build the most rigorous zero-cost market-intelligence arena we can. It knows the state of the world every day: leaders, conflicts, currencies, rates, the US–China AI race, regulation, companies and how they connect, what people talk about, and what insiders and politicians disclose. Agents turn that knowledge into decisions anyone can audit. The arena then tells us, honestly, whether any of it beats luck.

**The hard truth, from the literature** (section 5). For S&P 100 mega-caps, long-only, with ~0.4% round-trip costs:
- almost no published signal has a robust net edge at a days-to-weeks horizon;
- anomalies lose ~58% of their returns after publication;
- the average one earns a few basis points a month after costs;
- turning the book over weekly costs ~20% a year.

So "more factors" is not "better decisions". The design therefore does two things at once:
1. **Breadth of knowledge:** collect and connect everything that might matter, point-in-time, every day.
2. **Strict admission:** a new source or signal starts in **shadow mode** and influences no decision. It is admitted into agents' DNA only after proving predictive power out of sample with pre-registered tests (section 8). We expect most candidates to fail; the arena shows that openly.

**Main changes from v1.1:**

| Area | v1.1 | v2 |
|---|---|---|
| Information | Prices, then news and fundamentals | A **World Knowledge Base**: entities, relationships and events, bitemporal (section 3) |
| New signals | Added when built | **Signal Lab**: shadow mode, pre-registration, admission gates |
| Politicians and insiders | Not covered | Disclosure module, alerts and a "Mirror" species that copies disclosures (section 6) |
| Luck control | 10 live monkeys | 10 live monkeys **plus** ≥1,000 offline monkeys, best-of-N comparison, **null evolution** |
| Turnover | Revision every 5 days allowed | Rank bands and a cost-aware minimum holding period evolved within 10–60 trading days |
| AI | 3 layers | Encoders on everything, Qwen3.5-4B on triaged items, 9B for the daily world brief, parallel shards; GitHub Models and Cerebras dropped (retired / no longer free) |
| Reproducibility | "Same bytes" | **Replayable and auditable:** every raw AI output stored with model hash and runtime flags; decisions recomputed from stored readings are bit-exact |
| Product | Personal | English, swappable source adapters with a licence registry, Cloudflare Access login, privacy by design |

---

## 1. Rigour charter

These rules are fixed. Any change is logged in `rules/changes.md` with date and reason, and applies only going forward.

1. **Point-in-time or nothing.** Every datum carries `published_at` (when the world could know it) and `ingested_at` (when we stored it). A decision at time T sees only data with both ≤ T. Revised series use vintages (ALFRED); restated financials use the `filed` date; edited pages (Wikipedia, Wikidata) use revision timestamps or our own daily snapshots.
2. **Immutable raw archive.** Every fetch is stored as fetched, hashed and never edited. Corrections are new rows.
3. **Pre-registration.** Before a signal enters the Signal Lab, we write its hypothesis, expected sign, horizon, data and admission test. Results are reported even when they fail.
4. **Count every trial.** Every agent, parameter set, signal and generation ever evaluated is logged. The count N feeds every statistical haircut.
5. **Shadow before influence.** No new signal affects money until it passes the admission gates (section 8.3).
6. **Costs always on.** No result is shown without costs.
7. **Compare with luck.** Every claim of skill is measured against the distribution of the best of N random agents and against a null evolution.
8. **LLM look-ahead is contamination.** Any LLM reading dated before that model's training cutoff is excluded from evidence. Model versions are pinned.
9. **Audit trail.** Every decision links to the signals, readings, documents and source hashes behind it.
10. **No secrets or personal data in public.** Public repo and logs never contain raw source text, keys or personal data.

---

## 2. Architecture

```
 Sources ──► Adapters ──► Raw archive ──► Readers ──► World Knowledge Base ──► Signals ──► Agents ──► Market sim ──► Journal
 (registry   (one per     (immutable,     (encoders,   (entities, relations,   (feature    (DNA)      (costs,        (audit
  + licence)  source)      PIT, hashed)    LLMs)        events, bitemporal)     store, PIT)            dividends)     trail)
                                                                              │
                                                                              ▼
                                                                         Signal Lab (shadow, IC, admission)
                                                                              │
                                    Evaluation (DSR, MinTRL, monkeys, null evolution) ◄──┘
                                                                              │
                                                                              ▼
                                                                         Site (one-look 3D, login)
```

Each box is a separate module with a typed contract (schemas in code), so any piece can be replaced. A free source can become a licensed one, the local LLM can be swapped, the site can be rebuilt, all without touching the rest. This is what makes a later move to a real company cheap.

---

## 3. World Knowledge Base (WKB)

### 3.1 What it holds

| Layer | Examples | Main seeds |
|---|---|---|
| **Entities** | Companies (S&P 100 and their key suppliers, customers, competitors), people (CEOs, board members, heads of state, ministers, central bankers, members of Congress), governments and parties, countries, currencies, sectors, technologies (AI chips, LLMs, EVs, GLP-1), conflicts | Wikidata, SEC (`company_tickers.json`, Ex-21), congress.gov, FRED/ECB |
| **Relations** (time-bounded) | supplies / buys from / competes with / subsidiary of / executive of / board member of / holds stock in (disclosed) / member of party / regulates / exposed to country / exposed to technology / receives government contracts / lobbies on issue | 10-K text (customers and suppliers sections), Ex-21, Form 4, House/Senate disclosures, USAspending, LDA lobbying, Wikidata qualifiers |
| **Events** | Earnings, 8-K items, insider buys, guidance changes, product launches, recalls, FDA decisions, lawsuits, rules and executive orders, tariffs and export controls, elections, rate decisions, data releases, conflict escalations, index changes | EDGAR, Federal Register, Fed/ECB RSS, FRED release calendar, GDELT, openFDA, S&P DJI releases, news |
| **State** (daily snapshot) | Rates (Fed funds, €STR, **Euribor**, Treasury curve), FX (EUR/USD and majors), commodities, VIX, put/call, geopolitical risk (GPR), policy uncertainty (EPU), who governs where | Treasury XML, ECB, FRED/ALFRED, Cboe, GPR/EPU sites |
| **Narratives** | Running themes with evidence: "US–China AI race", "rate cuts", "tariffs", "GLP-1 boom", "data-centre power" | Clustering of news and events, summarised daily by the LLM |

### 3.2 Bitemporal model

Every fact or edge is one appended row:

`(subject_id, predicate, object_id | value, valid_from, valid_to, recorded_at, source_id, source_hash, extractor, extractor_version, confidence)`

- **"As known at T"** = `recorded_at ≤ T` and `valid_from ≤ T` and (`valid_to` empty or `> T`).
- Nothing is updated in place. A fact ends when a new row closes it. This keeps the knowledge base honest for replays and audits.
- Storage: daily immutable Parquet files in the private archive; DuckDB queries them in memory each night.
- We take the ideas of temporal knowledge-graph tools (bi-temporal edges, invalidation instead of deletion) without their servers or per-item LLM calls.

### 3.3 Daily World Brief

Each night the big local LLM writes a **World Brief as of T**: a structured summary of the state of the world and of each sector, built only from WKB facts and retrieved documents with timestamps ≤ T, with citations.
- It is an **input to humans and to the site**, and a candidate input to agents through derived signals (for example a sector "headwind/tailwind" score), which must pass the Signal Lab like any other.
- It is stored and never regenerated for past dates.

### 3.4 Retrieval (RAG)

- Embeddings: EmbeddingGemma-300M truncated to 256 dimensions (alternative: Qwen3-Embedding-0.6B).
- Search: exact cosine similarity in DuckDB. Approximate indexes (HNSW) are avoided because they make results non-deterministic, and at our size exact search is fast enough.
- Hard time filter: `published_at ≤ T` and `ingested_at ≤ T` on every query, including agents' own notes.

### 3.5 Entity linking

A deterministic dictionary of names, aliases and tickers (SEC, Wikidata) matched against GLiNER2 entity spans. The LLM is used only for ambiguous cases, and its choice is stored.

---

## 4. Source catalogue

Status was checked on 2026-11-13. Every source gets an adapter and a registry entry: licence, personal or commercial use, redistribution, rate limit, delay, PIT field, contact for the User-Agent, and the date the terms were last checked.

### 4.1 Tier A: integrate (phase 2)

| # | Source | Why | PIT field |
|---|---|---|---|
| 1 | SEC EDGAR: 8-K, Form 4, Form 144, 10-K/10-Q (daily index and Atom feed) | Legally timed corporate events and insider trades | `acceptanceDateTime` (after 17:30 ET means the next business day) |
| 2 | SEC XBRL companyfacts | Point-in-time fundamentals | `filed` |
| 3 | FRED **ALFRED** vintages + release calendar | Macro without revision leakage, and the economic calendar | `realtime_start` |
| 4 | BLS, BEA (keys) | CPI, payrolls, GDP | Release dates |
| 5 | US Treasury yield curve XML | Rates and curve shape, same day | Date |
| 6 | ECB Data Portal (€STR, **Euribor**, FX) | Euro rates and FX | Date |
| 7 | Fed and ECB RSS (statements, speeches) | Monetary policy | `pubDate` |
| 8 | Finnhub (news, earnings calendar), snapshotted daily | Company news and scheduled catalysts | Article time; our own snapshots |
| 9 | GDELT 2.0 Events + GKG filtered to our entities | Global events, tone, geopolitics, 15-minute cadence | `DATEADDED` |
| 10 | Federal Register API, incl. Public Inspection | Rules, executive orders, tariffs, export controls, seen the day before publication | Publication / inspection time |
| 11 | Wikipedia pageviews + Current Events portal | Cleanest free attention signal; curated daily events | Date; revision time |
| 12 | Wikidata (snapshotted daily) | Entities and relations, leaders, positions | Our snapshot date |
| 13 | FINRA daily short-sale volume | Same-day positioning proxy | Date |
| 14 | Cboe daily put/call, VIX family | Market fear and positioning | Date |
| 15 | S&P DJI index-change releases | Known flows | Press time |
| 16 | openFDA, FDA press RSS, ClinicalTrials.gov | Binary events for ~10 health names | Report date |
| 17 | House Clerk PTR + Senate eFD (self-parsed) | Politicians' trades (section 6) | Filing date (trades up to 45 days old) |
| 18 | congress.gov API, LDA lobbying (lda.gov), OpenFEC, USAspending | Who legislates, lobbies, funds and gets contracts | Action / filing dates |
| 19 | Bluesky Jetstream (cashtags, sampled), Hacker News (Algolia) | The only free, terms-clean social text | Post time |
| 20 | GPR and EPU indices | Geopolitical and policy-uncertainty regime | Release date (check for revisions) |

### 4.2 Tier B: later or backfill

ACLED (OAuth, EULA limits), Common Crawl News (too heavy nightly, good for backfill), NHTSA and CPSC recalls, WARN layoffs (CC BY bulk feed), USPTO patents (quarterly), FINRA short interest (8-day lag), 13F (45-day lag), YouTube (low value), Mastodon.

### 4.3 Excluded (not usable at zero cost or under their terms)

X API (pay-per-use since 2026), Stocktwits (scraping banned), Reddit (manual approval, non-commercial, new requests reportedly closing), Google Trends (alpha API only, pytrends archived, values rescaled per query, so not point-in-time), OpenSecrets API (closed), ProPublica Congress API (closed), House Stock Watcher (dead), Alpha Vantage (25 calls a day; at most one daily call), free options chains (no reliable source).

### 4.4 Terms and compliance

- Senate eFD and House disclosures **forbid commercial use** by statute (except news media). This is fine for the personal phase; for a product, this module needs legal review or a licensed source.
- Finnhub free is personal use only. Most outlet RSS forbids redistribution.
- Raw text never goes to the public repo: we store hashes, URLs and derived scores there.
- SEC and Wikimedia require a descriptive User-Agent with the project contact. SEC allows at most 10 requests per second.

---

## 5. Signal families and what the evidence says

Status: **Core** = in agents now; **Candidate** = admitted once the Signal Lab confirms it on our data; **Shadow** = hypothesis, logged and tested, no influence.

| Signal family | Evidence for US large caps | Horizon | Survives 0.4% costs? | Status |
|---|---|---|---|---|
| Cross-sectional momentum (12-1), industry momentum | Moderate; replicates; crash risk in rebounds | 1–12 months | Yes, with low turnover | **Core** |
| Trend on the index (risk on/off) | Moderate, as a drawdown filter | Weeks to months | Yes | **Core** (regime) |
| Low volatility / low beta | Moderate, risk-adjusted | Months | Yes | **Core** |
| Post-earnings drift, analyst revisions | Weak to contested in mega-caps since ~2006 | 1–60 days | Doubtful | Candidate |
| 52-week-high proximity | Overlaps momentum | Months | As a tilt | Candidate |
| Short-term reversal | Real gross, gone net in large caps | 1–20 days | No | Shadow |
| LLM news sentiment | Next-day effect, decaying as adoption grows; strongest in small caps | 1 day | No with next-open execution | Shadow (also feeds narratives) |
| Insider purchases (Form 4, cluster buys) | Strong overall, weak in mega-caps; rare in the S&P 100 | Weeks to months | Unproven | Shadow |
| Customer–supplier and peer lead–lag | Weak for mega-caps after publication | ~1 month | Probably not | Shadow |
| Attention (Wikipedia, social) | Short-lived push then reversal; WSB effect vanished after 2021 | Days | No | Shadow |
| Macro regime (GPR, EPU, rates) | Weak for picking stocks, useful for risk scaling | Months | As exposure scaling | Candidate (regime) |
| Congress trades | None for the average member after the STOCK Act; leaders possibly (small sample) | Months | No | Shadow (Mirror species) |
| 13F, 13D | Stale or rare in the S&P 100 | Months | Not shown | Shadow |
| Short interest / short-sale volume | Edge sits in small caps | Months | No evidence | Shadow |
| Government contracts, lobbying | Long-horizon effects only | Months to years | No | Shadow |
| Options-implied | Moderate historically; no free history | 1–4 weeks | Unclear | Excluded (no free data) |

**Design consequence.** The core gives agents a sound default. The knowledge breadth the project asks for feeds the Signal Lab, the World Brief and the site. Each piece earns a vote only by evidence. If years of shadow data show nothing, that is a valid, publishable result.

---

## 6. Politicians and insiders module

The goal: follow people with possible inside knowledge, alert on their trades, mimic them.

- **Only public, legal disclosures are used:** House and Senate periodic transaction reports, SEC Form 4 and 144 (insiders), 13D/G and 13F (funds). Trading on actual inside information is illegal; we study disclosures.
- **People graph:** member → party, committees (e.g. Armed Services, Energy, Financial Services), disclosed holdings and trades, donors and lobbying links; executive → company, roles, Form 4 history.
- **Alerts on the site:** a new disclosure appears as a pulse on the 3D scene (who, what, buy/sell, size range, delay since the trade).
- **Mirror species (Shadow, then live if admitted):** agents whose DNA copies disclosed trades. Parameters: whom to follow (all members, leaders, committee members relevant to the sector, insider cluster buys), size, holding period. They compete like everyone else, so the arena measures whether "copy the politicians" works after the disclosure delay.
- **Honest labels:** every Mirror trade shows the disclosure delay (often 20–45 days for Congress, 2 business days for Form 4).
- **"Possible informed trading" flags** are statistical only (for example an unusual trade before a committee action or a later event). They are never accusations; the wording says "pattern worth noting".

---

## 7. Agents v2

### 7.1 DNA additions

- Weights per admitted signal family (core plus admitted candidates).
- **Minimum holding period** and **rank band** (a held stock is sold only if it falls below rank K + band), evolved within 10–60 trading days. The 5-day revisions allowed in v1.1 would cost ~20% a year; the evidence favours ≥4 weeks.
- Regime response: exposure scaling from index trend, volatility, GPR and EPU.
- Sector caps.

### 7.2 Species (first generation)

| Species | Personality |
|---|---|
| Arrow | Momentum |
| Wave | Contrarian (kept as a control for reversal) |
| Rock | Quality and value (fundamentals once admitted) |
| Plumb | Balanced, low risk |
| Echo | Narrative and news (shadow inputs until admitted) |
| **Mirror** (new) | Copies disclosed trades of insiders and politicians |
| **Compass** (new) | Macro and regime rotation across sectors |

The MVP first used Portuguese species names; since the product is in English, they are Arrow, Wave, Rock, Echo and Plumb.

### 7.3 Reasoning agents (phase 5)

An LLM-reasoning species may be added later. It gets the same data, the same costs and the same rules; all its prompts and outputs are stored; it is labelled "free-reasoning, not bit-reproducible".

---

## 8. Evaluation: how we avoid fooling ourselves

### 8.1 Statistics shown for every agent

- Deflated Sharpe Ratio (DSR), using the cumulative trial count N (correlation-adjusted).
- Minimum Track Record Length (MinTRL): about 2.7 years for an annual Sharpe of 1.0, about 11 years for 0.5. Every leaderboard states this.
- Percentile versus the **best of N random agents**, with a block-bootstrap p-value (block length ≥ holding period).
- Alpha t-stat versus the market, momentum and low-volatility factors; equal-weight and cap-weight S&P 100 benchmarks.

### 8.2 Luck controls

1. Keep the 10 live monkeys as a sanity check.
2. Add **≥1,000 offline monkeys** each night with the same constraints (names, turnover, holding period, costs). Matching turnover is essential, otherwise we only measure cost differences.
3. **Null evolution:** run the same evolutionary process on monkeys. If evolved random agents produce equally good "winners", our selection is fitting noise.
4. **Merit badge** (replaces v1.1): at least 12 months of life, DSR ≥ 0.95, above the 95th percentile of the best-of-N monkeys, and beats the S&P 500 net of costs. Before that, the podium says **"provisional"**.

### 8.3 Signal Lab admission gates

A signal is admitted only if all of these hold:
- the hypothesis was pre-registered before testing;
- the daily rank information coefficient (signal vs. forward return at its horizon, from next open) is positive, with a Newey–West t > 3 over ≥ 250 properly adjusted observations;
- the IC has the same sign in at least 2 of 3 sub-periods;
- it adds value after controlling for momentum, low volatility and sector;
- the expected gross alpha exceeds turnover × cost;
- we apply a ~50% decay haircut to any published effect before sizing.

With 100 stocks, an IC of 0.02 is noise.

### 8.4 Holdout and history

- The live forward record from 2027-03-01 is the locked holdout. Nothing is tuned on it.
- Historical tests are allowed only for price and fundamental signals, labelled "technical rehearsal". They need a survivorship-free universe (historical S&P 100 membership) and purged, embargoed cross-validation. Probability of backtest overfitting (CSCV, 16 blocks) must stay below 0.2.

---

## 9. Zero-cost AI stack

| Role | Choice | Alternative |
|---|---|---|
| Runtime | llama.cpp, pinned release, grammar-constrained JSON | ik_llama.cpp |
| Sentiment, all items | FinBERT | FinSense-ModernBERT |
| Entities and event types, all items | GLiNER2 + SEC/Wikidata dictionary | GLiClass |
| Embeddings | EmbeddingGemma-300M (256-dim) | Qwen3-Embedding-0.6B |
| Structured reading, ~150 triaged items | Qwen3.5-4B Q4_K_M (Apache 2.0) | Gemma 4 E4B |
| Daily World Brief and narratives | Qwen3.5-9B Q4_K_M | Gemma 4 E4B Q8 |
| Optional second opinion | Cloudflare Workers AI free allocation (10,000 neurons/day) | Groq free plan |
| Dropped | GitHub Models (retired 2026-07-30), Cerebras (trial only), Hugging Face Inference (no free credits), OpenRouter free (50 a day) | — |

**Runtime plan.** Encoders on ~500 items: 10–20 minutes. LLM work runs as a matrix of 4–6 parallel jobs (free on public repos), sharded by `hash(item_id) mod N` and merged. Target wall time is 1–1.5 hours. To measure in week 1 with `llama-bench` on the runner.

**Reproducibility, stated honestly.** CPU types differ between runners, so LLM output bytes can drift. We pin everything (model sha256, llama.cpp release, threads, batch, seed, greedy decoding), log the CPU flags, and **store every raw output**. Replays use stored readings, so decisions are bit-exact. Re-running a model is a separate drift check, measured at label level.

**Model admission exam.** Unchanged from v1.1 (4.5): a frozen labelled exam, run with promptfoo or Inspect AI. A new model is swapped in only if it is clearly better and fits the time budget. A weekly job lists new GGUF releases (Qwen, Google, IBM Granite, Mistral, Liquid) and opens an issue; nothing changes automatically.

**Look-ahead.** Each model's training cutoff is recorded. Readings dated before it never count as evidence.

---

## 10. Infrastructure

- **Compute:** GitHub Actions on the public `arena-motor` repo (unlimited minutes, 4 vCPU / 16 GB). The nightly job is a matrix: ingest → read (sharded) → knowledge base → signals → agents → simulation → journal → site data.
- **Storage:** the private `arena-arquivo` repo holds append-only daily Parquet files (~0.3–0.5 GB a year). Embeddings are stored at 256-dim int8, or recomputed. No database binaries in Git. GGUF models live in `actions/cache`.
- **Site:** Cloudflare Pages, protected by Cloudflare Access (free up to 50 users; email code or GitHub login). Built from the private archive's site data, so nothing private becomes public.
- **Secrets:** GitHub secrets only. Logs print status, never data.

---

## 11. Product readiness

- **Language:** product in English (code, site, docs, repos, journal). Internal working notes stay in Portuguese.
- **Modularity:** typed contracts between modules; a source registry with licence and terms per source; any adapter can be replaced by a licensed feed.
- **Licensing path to commercial use:** before any commercial step, replace personal-use sources (Yahoo prices, Finnhub, outlet RSS, Senate/House disclosures) with licensed equivalents, and keep the official/open ones (SEC, FRED, ECB, Treasury, Federal Register, GDELT, Wikimedia).
- **Regulation (to check with a lawyer before going public or commercial):** publishing investment recommendations in the EU falls under the market-abuse rules (MAR) and possibly investment-advice licensing (MiFID II). The product must stay "research on simulated portfolios": no personalised advice, a clear disclaimer, and no "buy X" messages.
- **Privacy:** login through Cloudflare Access (no passwords stored by us); no third-party trackers; cookie-less analytics if any; a privacy notice; data about public figures limited to their official disclosures.
- **Accounts:** the project's own GitHub, Cloudflare and email, separate from anything else.
- **Code licence:** all rights reserved (decided 2026-11-13).

---

## 12. UX principles (for the site session)

- **One look, no scroll.** Each screen fits one viewport. Details open in place (panels, overlays), not in long pages.
- **Show, do not tell.** Encode meaning visually: size = value, height = beating the index, colour = species, glow = recent action, pulse = new disclosure or event, a translucent "luck band" for the monkeys.
- **Three gestures:** look (the arena), tap (an agent's visual card: DNA radar, value line vs. index and luck band, holdings as tiles, last decisions as icons), drill (the evidence behind a decision, with sources).
- **Words only as labels.** Numbers carry units; tooltips explain terms in one line; a "?" toggle reveals plain-English explanations.
- **Speed budget:** first meaningful paint < 1 s on broadband; 3D lazy-loaded after a static first frame; 60 fps on a mid-range laptop; a 2D fallback for low-power devices and accessibility.
- **Honesty is visible:** "provisional" vs. "merit" badges, the luck band, and the disclosure delay are always on screen.

---

## 13. Roadmap

| Phase | Content | Exit criterion |
|---|---|---|
| 1 (running) | MVP: prices, 20 agents + 10 monkeys + benchmarks, journal, nightly run; English translation; source registry | MVP viable (4 weeks stable) |
| Site (parallel) | Hosted one-look 3D site with login | The arena is visible with one look |
| 2a | WKB foundation: EDGAR events and Form 4, XBRL, ALFRED/BLS/BEA, Treasury, ECB (Euribor), Fed/ECB RSS, Federal Register, Wikidata snapshots, Wikipedia pageviews; Signal Lab with shadow IC; 1,000 offline monkeys; holding-period and rank-band DNA | Lab reports IC for all core and candidate signals |
| 2b | Readers: FinBERT, GLiNER2, embeddings, Qwen3.5-4B on triaged news, daily World Brief (9B), narratives; model exam | Readings stored, exam passed, runtime < 1.5 h |
| 2c | Politicians and insiders module, Mirror species (shadow), attention (Bluesky, HN), GDELT geopolitics, GPR/EPU, FDA/trials, index changes | Disclosures and alerts live on the site |
| 3 | Evolution with null evolution; merit badge v2 | First evolution with luck comparison published |
| Before 2027-03-01 | Freeze rules and universe; archive the rehearsal; official start | Start on Monday 2027-03-01 |
| 5 | Reasoning species, Europe, public opening (after legal check) | — |

Phase 2a must finish before the 2027-03-01 freeze, so the official arena starts with the improved DNA (holding period, rank bands) and the Signal Lab.

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| Overfitting through breadth | Shadow mode, pre-registration, trial count, DSR, null evolution |
| Free sources change or die (several did in 2026) | Adapter per source; registry with last-checked date; pipeline passes with any optional source down |
| Look-ahead via LLM memory or edited pages | Model cutoffs recorded; daily snapshots; bitemporal store |
| Runtime over 6 hours | Triage, matrix sharding, encoders-only fallback |
| Legal (disclosure data, recommendations) | Personal phase only; legal review before public or commercial use |
| Mistaking "interesting" for "predictive" | The site shows evidence status on every signal |
| Complexity outruns maintenance | Strict module contracts; tests per adapter; phases each deliver something visible |

---

## 15. Owner decisions

1. **Licence of the public code repo — decided 2026-11-13:** all rights reserved (source visible for transparency; no use or copying without permission). Keeps commercial options open.
2. Everything else follows earlier owner decisions.

---

## Appendix: references

Evidence (section 5 and 8):
- Chen & Velikov (2023) JFQA: https://doi.org/10.1017/S0022109022000874
- McLean & Pontiff (2016) JF: https://doi.org/10.1111/jofi.12365
- Jensen, Kelly & Pedersen (2023) JF: https://doi.org/10.1111/jofi.13249
- Martineau (2022), PEAD: https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf
- Moskowitz, Ooi & Pedersen (2012) JFE: https://doi.org/10.1016/j.jfineco.2011.11.003
- Cohen, Malloy & Pomorski (2012) JF: https://doi.org/10.1111/j.1540-6261.2012.01740.x
- Belmont et al. (2022) JPubE, Congress trades: https://ideas.repec.org/a/eee/pubeco/v207y2022ics0047272722000044.html
- Lopez-Lira & Tang (v6, 2025): https://arxiv.org/abs/2304.07619
- Glasserman & Lin (2023), LLM look-ahead: https://arxiv.org/abs/2309.17322
- He, Lv, Manela & Wu (2025), chronologically consistent LLMs: https://arxiv.org/abs/2502.21206
- Da, Engelberg & Gao (2011) JF: https://doi.org/10.1111/j.1540-6261.2011.01679.x
- Bradley et al. (2024) RFS, WSB: https://econpapers.repec.org/RePEc:oup:rfinst:v:37:y:2024:i:5:p:1409-1459
- Caldara & Iacoviello (2022), GPR: https://www.matteoiacoviello.com/gpr.htm
- Baker, Bloom & Davis (2016), EPU: https://www.policyuncertainty.com
- Harvey, Liu & Zhu (2016) RFS: https://doi.org/10.1093/rfs/hhv059
- Bailey & López de Prado (2014), Deflated Sharpe Ratio: https://ssrn.com/abstract=2460551
- Bailey & López de Prado (2012), MinTRL: https://ssrn.com/abstract=1821643
- Bailey et al. (2017), PBO: https://ssrn.com/abstract=2326253

Sources and infrastructure (section 4, 9, 10):
- SEC EDGAR access rules: https://www.sec.gov/os/accessing-edgar-data
- BLS API: https://www.bls.gov/developers/api_faqs.htm
- Treasury yield XML: https://home.treasury.gov/treasury-daily-interest-rate-xml-feed
- Fed RSS: https://federalreserve.gov/feeds
- GDELT: https://www.gdeltproject.org/data.html
- Wikimedia API access policy: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html
- congress.gov API: https://github.com/LibraryOfCongress/api.congress.gov
- LDA lobbying API: https://lda.senate.gov/api
- api.data.gov limits: https://api.data.gov/docs/developer-manual
- Senate eFD: https://efdsearch.senate.gov/search/
- FINRA short-sale volume: https://www.finra.org/finra-data/browse-catalog/short-sale-volume
- Cboe daily statistics: https://www.cboe.com/us/options/market_statistics/daily/
- openFDA: https://open.fda.gov/apis/authentication
- Bluesky Jetstream: https://bsky.network/docs/jetstream
- HN Algolia: https://hn.algolia.com/api
- Finnhub pricing: https://finnhub.io/pricing
- Stocktwits terms: https://stocktwits.com/terms
- GitHub Models retirement: https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models
- Cloudflare Workers AI pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
- Groq limits: https://console.groq.com/docs/rate-limits
- Gemini terms: https://aistudio.google.com/docs/terms
- OpenRouter limits: https://openrouter.ai/docs/api/reference/limits
- DuckDB vector search: https://duckdb.org/docs/current/core_extensions/vss
- Qwen3.5 small models: https://artificialanalysis.ai/articles/qwen3-5-small-models
- GLiNER2: https://arxiv.org/html/2507.18546v1
- EmbeddingGemma: https://huggingface.co/google/embeddinggemma-300m

Some quota figures come from secondary sources and must be re-checked when each adapter is built.
