// Ask v2: read-only access to the site's own data files, "as known" on a chosen day.
// The Pages Function reads them through env.ASSETS (same deployment, behind the login); the exam reads
// a frozen snapshot from disk. Nothing here ever writes.
import { UNIVERSE } from "./universe.js";

export const CAPITAL = 100000;

// Plain names for companies whose official names read badly in a sentence.
const SHORT = {
  "Apple Inc.": "Apple", "Visa Inc.": "Visa", "Netflix, Inc.": "Netflix", "Adobe Inc.": "Adobe",
  "Walt Disney Company (The)": "Walt Disney", "Coca-Cola Company (The)": "Coca-Cola", "Home Depot (The)": "Home Depot",
  "Berkshire Hathaway (Class B)": "Berkshire Hathaway", "Alphabet Inc. (Class A)": "Alphabet (Google, class A)",
  "Alphabet Inc. (Class C)": "Alphabet (Google, class C)", "Eli Lilly and Company": "Eli Lilly", "Chevron Corporation": "Chevron",
  "Danaher Corporation": "Danaher", "Union Pacific Corporation": "Union Pacific", "Linde plc": "Linde", "Merck & Co.": "Merck",
  "Goldman Sachs": "Goldman Sachs", "Bank of America": "Bank of America",
};
// Words people use for companies that are not in the official name.
const ALIASES = {
  google: "GOOGL", alphabet: "GOOGL", facebook: "META", meta: "META", "j&j": "JNJ", "johnson and johnson": "JNJ",
  "coke": "KO", "coca cola": "KO", "p&g": "PG", "procter and gamble": "PG", "berkshire": "BRK.B", "jp morgan": "JPM",
  "jpmorgan": "JPM", "exxon": "XOM", "disney": "DIS", "lilly": "LLY", "eli lilly": "LLY", "mcdonalds": "MCD", "mcdonald's": "MCD",
  "lowes": "LOW", "lowe's": "LOW", "at&t": "T", "verizon": "VZ", "amazon": "AMZN", "tesla": "TSLA", "nvidia": "NVDA",
  "microsoft": "MSFT", "starbucks": "SBUX", "altria": "MO", "philip morris": "PM", "unitedhealth": "UNH", "united health": "UNH",
  "salesforce": "CRM", "accenture": "ACN", "home depot": "HD", "3m": "MMM", "pepsi": "PEP", "pepsico": "PEP",
};

export function companyName(t) {
  const row = UNIVERSE.find(r => r[0] === t);
  const n = row ? row[1] : t;
  return SHORT[n] || n;
}
export function companySector(t) { return UNIVERSE.find(r => r[0] === t)?.[2] || null; }

export function makeStore(loadJson) {
  const cache = new Map();
  const get = path => { if (!cache.has(path)) cache.set(path, Promise.resolve(loadJson(path)).catch(() => null)); return cache.get(path); };
  return {
    arena: () => get("arena.json"),
    journal: d => get(`journal/${d}.json`),
    shard: d => get(`days/${d}.json`),
    docs: () => get("intel/docs.json"),
    alerts: () => get("intel/alerts.json"),
    lab: () => get("lab/report.json"),
    tree: () => get("evolution/tree.json"),
    merit: () => get("merit/report.json"),
  };
}

// Everything the tools need, prepared once per request from arena.json (as of `asOf`, or the last night).
export async function prepare(store, asOf) {
  const A = await store.arena();
  if (!A) throw new Error("no-data");
  const dates = A.meta.dates;
  const day = asOf && dates.includes(asOf) ? asOf : asOf ? (dates.filter(d => d <= asOf).pop() || dates[0]) : dates[dates.length - 1];
  const di = dates.indexOf(day), latest = day === dates[dates.length - 1];
  const byId = {}, P = [];
  for (const p of [...A.p, ...(A.dead || [])]) {
    const off = dates.indexOf(p.from || dates[0]);
    const k = di - off;
    if (k < 0) continue;                         // not born yet on that day
    const v = p.s[Math.min(k, p.s.length - 1)];
    const series = p.s.slice(0, k + 1).map((x, j) => [dates[off + j], x]);
    const x = { ...p, v, retD: v / p.s[0] - 1, series, start: p.s[0], dead: !!p.dead && latest };
    byId[p.id] = x; P.push(x);
  }
  const idx = P.find(p => p.type === "index");
  for (const p of P) {   // versus the index over the same window (newborns: since their own birth)
    const off = dates.indexOf(p.from || dates[0]), io = dates.indexOf(idx.from || dates[0]);
    const i0 = idx.s[off - io], i1 = idx.s[di - io];
    p.idxD = i0 && i1 ? i1 / i0 - 1 : null;
    p.vsD = p.idxD == null ? null : p.retD - p.idxD;
  }
  const agents = P.filter(p => p.type === "agent" && !p.dead);
  const ranked = [...agents].sort((a, b) => (b.vsD ?? -9) - (a.vsD ?? -9));
  ranked.forEach((p, i) => { p.rank = i + 1; });
  return { A, store, dates, day, di, latest, byId, P, agents, ranked, idx, eq: P.find(p => p.type === "equal"), monkeys: P.filter(p => p.type === "monkey") };
}

// ---------- plain formatting ----------
export const eur = x => (x < 0 ? "-" : "") + "EUR " + Math.round(Math.abs(x)).toLocaleString("en-GB");
export const pct = (x, d = 2) => x == null ? "n/a" : (x > 0 ? "+" : x < 0 ? "-" : "") + Math.abs(x * 100).toFixed(d) + "%";
export const pts = (x, d = 2) => x == null ? "n/a" : (x > 0 ? "+" : x < 0 ? "-" : "") + Math.abs(x * 100).toFixed(d) + " points";
export const dayName = d => { const t = new Date(d + "T12:00:00Z"); return `${t.getUTCDate()} ${t.toLocaleString("en-GB", { month: "long", timeZone: "UTC" })} ${t.getUTCFullYear()}`; };
export const dayShort = d => { const t = new Date(d + "T12:00:00Z"); return `${t.getUTCDate()} ${t.toLocaleString("en-GB", { month: "short", timeZone: "UTC" })}`; };
export const tone = x => x > 0.00005 ? "gain" : x < -0.00005 ? "loss" : "flat";

// What each signal means, in plain words (positive reading / negative reading).
export const SIGNAL_PLAIN = {
  mom_1m: ["rose over the last month", "fell over the last month", "1-month trend"],
  mom_3m: ["rose over the last 3 months", "fell over the last 3 months", "3-month trend"],
  mom_6m: ["rose steadily over 6 months", "fell over 6 months", "6-month trend"],
  mom_12m: ["rose over the past year", "fell over the past year", "12-month trend"],
  rev_1w: ["dipped last week (a possible bargain)", "rose last week (less of a bargain)", "last week's drop"],
  rev_1m: ["fell last month (a possible bargain)", "rose last month (less of a bargain)", "last month's drop"],
  low_risk: ["moves calmly (low risk)", "moves a lot (higher risk)", "low risk"],
  near_high: ["is close to its 1-year high", "is far below its 1-year high", "near the 1-year high"],
  news: ["is in good news", "is in bad news", "news"],
  value: ["looks cheap for its earnings", "looks expensive for its earnings", "value"],
  quality: ["is a high-quality business", "is a lower-quality business", "quality"],
};
export const CAUSE_PLAIN = {
  entry: "a new purchase: it ranked among the agent's top picks",
  rebalance: "a resize back to the agent's target weight",
  stop_loss: "a stop loss: the share fell more than the agent allows",
  rank_band: "an exit: the share dropped out of the agent's keep zone in the ranking",
  brake: "the safety brake: the market is below its 200-day average, so the agent invests less",
  swap: "a swap for a better-ranked share",
};
