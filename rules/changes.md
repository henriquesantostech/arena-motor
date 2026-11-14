# Rule changes

Every change is logged here with its date and reason, and applies only from then on.

| Date | Version | Change | Reason |
|---|---|---|---|
| 2026-11-13 | 1.0 | Initial rules (design v1.1) | Start of the trial |
| 2026-11-13 | 1.0 | A night that fails is processed on the next run, day by day, in order, using only the data up to that day (the design said that night's orders were lost) | Results never depend on infrastructure failures, and any night replays identically |
| 2026-11-13 | 1.0 | Until news, value and quality signals exist (phase 2), the News and Value & Quality species use provisional weights on price signals | The MVP only has prices |
| 2026-11-13 | 1.0 | Product language is English (code, rules, journal, justifications). Participants renamed (Arrow, Wave, Rock, Echo, Keel, Monkey); monkeys keep their original random-draw identifier (`seed_id`) | Product quality; renaming must not change any result |
| 2026-11-14 | 1.1 | **Effective 2026-11-16.** DNA gains `min_hold_days` (10–60 trading days) and `rank_band`: on a review day a holding leaves only if it ranks below `n_holdings + rank_band` **and** has been held at least `min_hold_days` (stop loss and the maximum weight still apply every day). The score-threshold swap no longer applies. Living participants receive the fields on the effective date (logged in that night's journal under `rule_changes`); monkeys copy the values of the agent whose management they copy | Design v2 §7.1: at ~0.4% per round trip, weekly turnover costs ~20% a year. On the 53-night rehearsal, applying it from day one cut the agents' trading by a third and their costs by a quarter |
| 2026-11-14 | 1.1 | Signal Lab (design v2 §8.3) runs every night in shadow mode: daily rank IC, residual IC, Newey–West t, sub-period signs, haircut alpha vs turnover cost; the 8 price signals are pre-registered in `rules/signals/` | Rigour charter: shadow before influence; no signal changes money without passing the gates and a logged rule change |
| 2026-11-13 | 1.0 | Balanced species renamed Keel → **Plumb** (ex-Prumo), as in design v2 §7.2. Names only; no result changes | Align with design v2 |
