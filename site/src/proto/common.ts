// Experience v3 prototypes: shared plain-language helpers and the DNA → creature mapping.
// One identity everywhere: the same parameters draw the creature in 2D (SVG) and in 3D.
import type { Arena, Model, Move, Participant } from "../data";

export const capital = (A: Arena) => A.meta.capital || 100000;
export const euro = (x: number | null | undefined, sign = false) =>
  x == null ? "—" : (sign && x > 0 ? "+" : x < 0 ? "−" : "") + "€" + Math.round(Math.abs(x)).toLocaleString("en-GB");
export const pc = (x: number | null | undefined, d = 1) =>
  x == null ? "—" : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x * 100).toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d }) + "%";
export const dayName = (d?: string | null) => d ? new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "long", timeZone: "UTC" }) : "";
export const company = (A: Arena, t: string) => (A.meta as unknown as { companies?: Record<string, { name: string }> }).companies?.[t]?.name?.replace(/,? (Inc\.?|Corporation|Corp\.?|Company|Co\.|plc|N\.V\.|Holdings|Incorporated|& Co\.)$/i, "") || t.replace("^SP500TR", "the S&P 500");

// ---------- the species, in plain words ----------
export const STRATEGY: Record<string, string> = {
  arrow: "Rides what is rising", wave: "Buys what fell too far", rock: "Holds calm, solid companies",
  echo: "Reacts to recent moves", plumb: "A bit of everything, carefully", mirror: "Copies insiders' trades", compass: "Follows the big picture",
};
export const SPECIES_HUE: Record<string, number> = { arrow: 24, wave: 268, rock: 160, echo: 46, plumb: 212, mirror: 330, compass: 186 };

// ---------- DNA → creature ----------
export interface Creature { lean: number; elong: number; spikes: number; round: number; lobes: number; breath: number; hue: number; seed: number; stone: boolean }
export function creatureOf(p: Participant): Creature {
  const w = p.dna?.w || {};
  const g = (k: string) => (w[k] || 0) / 100;
  const momentum = g("mom_1m") + g("mom_3m") + g("mom_6m") + g("mom_12m") + g("near_high");
  const contrarian = g("rev_1w") + g("rev_1m");
  const calm = g("low_risk") + g("value") + g("quality");
  const review = p.dna?.review || 10, picks = p.dna?.picks || 10;
  let seed = 0; for (const ch of p.name) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
  return {
    lean: momentum * 0.45, elong: 1 + momentum * 0.7, spikes: Math.min(1, contrarian * 1.6), round: Math.min(1, calm * 1.8),
    lobes: Math.round(4 + Math.min(6, picks / 4)), breath: 1.6 + Math.min(5, review / 10), hue: SPECIES_HUE[p.sp || ""] ?? 210, seed,
    stone: !!p.dead,
  };
}

/** Closed SVG path of the creature's body, centred on 0,0, about `r` in radius. `t` animates breathing. */
export function bodyPath(c: Creature, r: number, t = 0) {
  const n = 72, pts: string[] = [];
  const breathe = 1 + 0.035 * Math.sin((t / c.breath) * Math.PI * 2);
  for (let k = 0; k < n; k++) {
    const a = (k / n) * Math.PI * 2;
    const spike = c.spikes * 0.42 * Math.pow(Math.max(0, Math.cos(c.lobes * a + c.seed)), 6);
    const wobble = (1 - c.round) * 0.08 * Math.sin(3 * a + c.seed * .7);
    let rr = r * breathe * (1 + spike + wobble);
    let x = Math.cos(a) * rr * c.elong, y = Math.sin(a) * rr / Math.sqrt(c.elong);
    x += -y * c.lean;                                          // leaning forward (to the right)
    pts.push(`${x.toFixed(2)},${y.toFixed(2)}`);
  }
  return "M" + pts.join("L") + "Z";
}
export const creatureFill = (c: Creature, dark: boolean, alpha = 1) =>
  c.stone ? `hsla(220, 6%, ${dark ? 42 : 66}%, ${alpha})` : `hsla(${c.hue}, ${dark ? 48 : 52}%, ${dark ? 62 : 52}%, ${alpha})`;

// ---------- the answer-first sentences ----------
export function headline(M: Model, i: number) {
  const A = M.A, idx = M.index, cap = capital(A);
  if (!idx || i === 0) return { big: `All ${M.agents.length} agents start with ${euro(cap)} of pretend money.`, small: "The race starts at the next market open." };
  const r = M.retAt(idx, i), up = r >= 0;
  const better = M.agents.filter(p => M.gapAt(p, i) > 0);
  const band = M.luckAt(i), beyond = band ? better.filter(p => M.gapAt(p, i) > band[1]).length : 0;
  const allLost = M.agents.every(p => M.retAt(p, i) < 0);
  const big = `Since ${dayName(A.meta.dates[0])} the market is ${up ? "up" : "down"} ${pc(Math.abs(r)).replace(/^[+−]/, "")}. ${better.length} of ${M.agents.length} agents did better than just buying it.`;
  const small = `${euro(cap)} in the market is now ${euro(cap * (1 + r))}.` + (allLost && !up ? " Every agent lost money; the best lost less." : "")
    + (better.length ? (beyond ? ` ${beyond} of them ${beyond === 1 ? "is" : "are"} clearly beyond luck.` : " None is clearly beyond luck yet.") : "");
  return { big, small };
}

/** "Bought Altria because it was steady and had fallen a lot." */
const WHY: Record<string, [string, string]> = {
  mom_1m: ["it had been rising this month", "it had stopped rising"], mom_3m: ["it had been rising for months", "its rise had faded"],
  mom_6m: ["it had risen for half a year", "its long rise had faded"], mom_12m: ["it had risen all year", "its yearly rise had faded"],
  rev_1w: ["it had dropped last week", "it had bounced back"], rev_1m: ["it had fallen a lot this month", "it had recovered"],
  low_risk: ["it was steady", "it had become jumpy"], near_high: ["it was near its yearly high", "it had slipped from its high"],
  news: ["the news was good", "the news turned"], value: ["it looked cheap", "it no longer looked cheap"], quality: ["it was a solid business", "it looked less solid"],
};
export function sentence(A: Arena, m: Move): string {
  const name = company(A, m.t), r = m.r;
  if (m.k === "dividend") return `Received a dividend from ${name}.`;
  if (m.k === "split") return `${name} split its shares.`;
  if (m.k === "cancelled") return `An order for ${name} could not be filled.`;
  if (m.k === "sell") {
    if (r?.cause === "stop_loss") return `Sold ${name} after it fell too far.`;
    if (r?.cause === "rank_band") return `Sold ${name}: it was no longer among its favourites.`;
    if (r?.cause === "delisting") return `Sold ${name}: it left the stock market.`;
    const by = (m.why || "").match(/replaced by ([A-Z.^]+)/)?.[1];
    if (by) return `Sold ${name} to make room for ${company(A, by)}.`;
    if (r?.cause === "rebalance") return `Trimmed ${name} to keep the portfolio balanced.`;
    const d = (r?.drivers || []).filter(x => x.term < 0).slice(0, 2).map(x => WHY[x.s]?.[1]).filter(Boolean);
    return `Sold ${name}${d.length ? " because " + d.join(" and ") : ""}.`;
  }
  const d = (r?.drivers || []).filter(x => x.term > 0).slice(0, 2).map(x => WHY[x.s]?.[0]).filter(Boolean);
  if (r?.seed) return `Bought ${name} at random (a monkey).`;
  return `Bought ${name}${d.length ? " because " + d.join(" and ") : ""}.`;
}

/** Plain DNA: what it cares about, 0–5 dots. */
export function caresAbout(p: Participant): { label: string; dots: number }[] {
  const w = p.dna?.w || {}; const g = (ks: string[]) => ks.reduce((a, k) => a + (w[k] || 0), 0);
  const rows = [
    { label: "Things that are rising", v: g(["mom_1m", "mom_3m", "mom_6m", "mom_12m", "near_high"]) },
    { label: "Things that fell too far", v: g(["rev_1w", "rev_1m"]) },
    { label: "Calm, steady companies", v: g(["low_risk"]) },
    { label: "Cheap, solid businesses", v: g(["value", "quality"]) },
    { label: "The news", v: g(["news"]) },
  ];
  return rows.map(r => ({ label: r.label, dots: Math.round(Math.min(100, r.v) / 20) }));
}
