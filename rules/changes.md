# Rule changes

Every change is logged here with its date and reason, and applies only from then on.

| Date | Version | Change | Reason |
|---|---|---|---|
| 2026-11-13 | 1.0 | Initial rules (design v1.1) | Start of the trial |
| 2026-11-13 | 1.0 | A night that fails is processed on the next run, day by day, in order, using only the data up to that day (the design said that night's orders were lost) | Results never depend on infrastructure failures, and any night replays identically |
| 2026-11-13 | 1.0 | Until news, value and quality signals exist (phase 2), the News and Value & Quality species use provisional weights on price signals | The MVP only has prices |
| 2026-11-13 | 1.0 | Product language is English (code, rules, journal, justifications). Participants renamed (Arrow, Wave, Rock, Echo, Keel, Monkey); monkeys keep their original random-draw identifier (`seed_id`) | Product quality; renaming must not change any result |
