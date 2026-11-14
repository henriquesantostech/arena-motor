// Synthetic arena data (no real market data: the engine repository is public) for the performance
// check and for working on the site without the private archive.
// Usage: node scripts/fixture.mjs <folder>   -> writes <folder>/data/arena.json and data/days/*.json
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const out = process.argv[2] || ".perf";
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const days = []; for (let d = new Date("2026-08-28T12:00:00Z"); days.length < 60; d.setUTCDate(d.getUTCDate() + 1)) if (d.getUTCDay() % 6) days.push(d.toISOString().slice(0, 10));
const walk = (drift, vol) => { let v = 100000; return days.map((_, i) => i === 0 ? v : (v *= 1 + drift + (rnd() - .5) * vol)); };
const sp = { Trend: "Arrow", Contrarian: "Wave", "Value & Quality": "Rock", News: "Echo", Balanced: "Plumb" };
const keys = Object.values(sp).map(s => s.toLowerCase());
const signals = ["Trend 1M", "Trend 3M", "Trend 6M", "Trend 12M", "Dip 1W", "Dip 1M", "Low risk", "Near high", "News", "Value", "Quality"];
const tick = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM", "LLY", "AVGO", "COST", "PG", "KO", "PEP", "MRK"];
const idx = walk(.0005, .012);
const P = [];
const mk = (name, type, s, sp) => {
  const v = s.at(-1), ret = v / s[0] - 1, ir = idx.at(-1) / idx[0] - 1;
  const hold = type === "index" ? [] : tick.slice(0, 8 + Math.floor(rnd() * 6)).map(t => ({ t, name: t, n: 10, eur: 0, w: 0, gain: (rnd() - .4) * .2, since: days[3] }));
  hold.forEach(h => { h.w = 1 / hold.length * .97; h.eur = h.w * v; });
  return {
    id: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""), name, type, sp, born: days[0], parents: null, copies: type === "monkey" ? "Arrow-01" : null,
    value: Math.round(v * 100) / 100, ret, vsIdx: type === "index" ? 0 : ret - ir, score: (ret - ir) * 10, beatsMonkeys: rnd(), merit: type === "agent" ? false : null,
    vol: .15, mdd: .05 + rnd() * .05, fees: 120, divs: 40, turnover: 3, hit: .5, closed: 10, tax: 0, cash: v * .03, days: days.length - 1,
    s: s.map(x => Math.round(x * 100) / 100), from: days[0],
    dna: type === "agent" ? { w: Object.fromEntries(signals.map((k, i) => [k, i < 4 ? 25 : 0])), picks: 10, maxW: .15, review: 5, stop: .12, brake: .5 } : null,
    hold, next: [], log: [{ d: days.at(-1), k: "buy", t: "AAPL", eur: 9000, why: "Entry: synthetic example." }], pctAll: type === "agent" ? rnd() : null, pctMirror: type === "agent" ? rnd() : null,
  };
};
keys.forEach(k => { for (let i = 1; i <= 4; i++) P.push(mk(`${k[0].toUpperCase() + k.slice(1)}-0${i}`, "agent", walk(.0004 + (rnd() - .5) * .002, .015), k)); });
for (let i = 1; i <= 10; i++) P.push(mk(`Monkey-${String(i).padStart(2, "0")}`, "monkey", walk(.0004, .015), null));
P.push(mk("Equal weight", "equal", walk(.0005, .011), null));
P.push(mk("S&P 500 (EUR)", "index", idx, null));
const A = {
  meta: { mode: "trial", dayZero: days[0], capital: 100000, rules: "1.1", engine: "fixture", updated: days.at(-1), dates: days },
  species: Object.fromEntries(Object.entries(sp).map(([f, l]) => [l.toLowerCase(), { label: l, family: f, about: "Synthetic" }])),
  p: P, band: days.map(() => [97000, 104000]),
  luck: { n: 1000, date: days.at(-1), p05: -.03, median: .01, p95: .06, best: .1, s: days.map((_, i) => [-.03 * i / days.length, .06 * i / days.length]) },
  day: { date: days.at(-1), buys: 12, sells: 9, spx: .004, eurusd: 1.1, aboveMa200: true, orders: 5, excluded: 0 },
};
mkdirSync(join(out, "data", "days"), { recursive: true });
writeFileSync(join(out, "data", "arena.json"), JSON.stringify(A));
days.forEach((d, i) => writeFileSync(join(out, "data", "days", d + ".json"), JSON.stringify({ date: d, values: Object.fromEntries(P.map(p => [p.id, p.s[i]])) })));
console.log(`fixture: ${P.length} participants, ${days.length} days -> ${out}/data`);
