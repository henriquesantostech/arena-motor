// Data model of the site. The engine writes data/arena.json (latest night) and data/days/<date>.json
// (one shard per night, for the Time Machine). Everything here is read-only and derived in the browser.

export type Kind = "agent" | "monkey" | "index" | "equal";

export interface Driver { s: string; z: number; w: number; term: number; raw?: number | null }
export interface Reason { cause?: string; score?: number; rank?: number; of?: number; seed?: string; drivers?: Driver[] }
export interface Move { d: string; dd?: string | null; k: string; t: string; eur?: number | null; px?: number; n?: number; fee?: number; gain?: number | null; why?: string; ratio?: number; r?: Reason | null }
export interface Holding { t: string; name: string; n: number; eur: number; w: number; gain: number | null; since: string }
export interface Dna { w: Record<string, number>; picks?: number; maxW?: number; review?: number; stop?: number | null; brake?: number; minHold?: number | null; band?: number | null }

export interface Participant {
  id: string; name: string; type: Kind; sp: string | null; born: string; parents?: string[] | null; copies?: string | null;
  value: number; ret: number; vsIdx: number | null; score: number | null; beatsMonkeys: number | null; merit: boolean | null;
  vol: number | null; mdd: number; fees: number; divs: number; turnover: number; hit: number | null; closed: number;
  tax: number; cash: number; days: number; s: number[]; from: string; dna: Dna | null; hold: Holding[];
  next: { k: string; t: string; eur?: number | null; all?: boolean; why?: string; dd?: string; r?: Reason | null }[]; log: Move[];
  pctAll?: number | null; pctMirror?: number | null;
  dead?: { died: string; evaluation: number; rank: number; of: number; vs_index: number; value: number; fitness?: number } | null;
  badge?: "provisional" | "merit" | "rehearsal" | "dead" | null; badgeMissing?: string[] | null; generation?: number | null; immigrant?: boolean | null;
}

export interface Luck { n: number; date: string; p05: number | null; median: number | null; p95: number | null; best: number | null; s: ([number, number] | null)[] }

export interface Arena {
  meta: {
    mode: "trial" | "live"; dayZero: string; capital: number; rules: string; engine: string; updated: string | null; dates: string[];
    marks?: { d: string; k: string; label: string }[]; signals?: Record<string, string>;
    generation?: number; meritEvidence?: string | null;
    evidence?: Record<string, { status: string | null; obs: number | null; ic: number | null; t: number | null }>;
  };
  fillsByDay?: Record<string, string[]>;
  species: Record<string, { label: string; family: string; about: string }>;
  p: Participant[];
  dead?: Participant[];   // the graveyard: read-only cards, never in rankings
  band: ([number, number] | null)[];
  luck?: Luck | null;
  day: { date: string; buys: number; sells: number; spx: number | null; eurusd: number | null; aboveMa200: boolean | null; orders: number; excluded: number } | null;
}

export interface Model {
  A: Arena;
  byId: Record<string, Participant>;
  agents: Participant[];      // ranked
  monkeys: Participant[];
  index?: Participant;
  equal?: Participant;
  order: Participant[];       // ranked agents, benchmarks, monkeys (card navigation)
  species: string[];
  scored: boolean;            // ranking by score (enough history) or by gap to the index
  moved: boolean;             // false on day zero
  luck: [number, number] | null;   // luck band, as a gap to the index (same unit as the height in the world)
  luckN: number;              // monkeys behind the band (1,000 offline, or the 10 live ones)
  lucky: number | null;       // agents above the band
  active: Set<string>;        // traded at the last open
  rank: Record<string, number>;
  gap(p: Participant): number;
  last: number;                                   // index of the latest night
  // Time Machine: everything as it was on night i
  retAt(p: Participant, i: number): number;
  gapAt(p: Participant, i: number): number;
  valueAt(p: Participant, i: number): number;
  luckAt(i: number): [number, number] | null;
  rankAt(i: number): { agents: Participant[]; rank: Record<string, number> };
  activeAt(i: number): Set<string>;
  span: number;                                   // largest gap to the index over the whole season (stable height scale)
  medianAt(i: number): number;                    // median agent value on night i (crystal size is relative to it)
}

export interface Shard {
  date: string; inputs?: Record<string, unknown>; journalSha256?: string | null; version?: Record<string, string>;
  sig: { cols: string[]; z: Record<string, number[]>; raw: Record<string, (number | null)[]>; sha256: string };
  excluded: string[]; delisted: string[]; values: Record<string, number>; positions: Record<string, Record<string, number>>;
  market?: { eurusd?: number; sp500?: number; above_ma?: boolean };
}
const shardCache = new Map<string, Promise<Shard>>();
export function loadShard(d: string): Promise<Shard> {
  if (!shardCache.has(d)) shardCache.set(d, fetch(`${ROOT}data/days/${d}.json`).then(r => { if (!r.ok) throw new Error("shard " + r.status); return r.json(); }));
  return shardCache.get(d)!;
}

export const ROOT = document.documentElement.dataset.root ?? "./";
export async function loadArena(base = ROOT): Promise<Arena> {
  const r = await fetch(base + "data/arena.json", { cache: "no-cache" });
  if (!r.ok) throw new Error("data " + r.status);
  return r.json();
}

export function buildModel(A: Arena): Model {
  const P = A.p;
  const byId = Object.fromEntries([...P, ...(A.dead || [])].map(p => [p.id, p]));
  const index = P.find(p => p.type === "index"), equal = P.find(p => p.type === "equal");
  const raw = P.filter(p => p.type === "agent");
  const scored = raw.length > 0 && raw.every(p => p.score != null);
  const agents = raw.slice().sort((a, b) => scored ? (b.score! - a.score!) : ((b.vsIdx ?? b.ret ?? 0) - (a.vsIdx ?? a.ret ?? 0)) || a.name.localeCompare(b.name));
  const rank: Record<string, number> = {};
  agents.forEach((p, i) => rank[p.id] = i + 1);
  const monkeys = P.filter(p => p.type === "monkey").sort((a, b) => (b.ret || 0) - (a.ret || 0));
  const moved = raw.some(p => Math.abs(p.ret || 0) > 1e-6);
  const gap = (p: Participant) => p.type === "index" ? 0 : (p.vsIdx ?? 0);
  const idxRet = index?.ret ?? 0;
  const L = A.luck;
  const mg = monkeys.map(gap);
  const luck: [number, number] | null = !moved ? null
    : L && L.p05 != null && L.p95 != null ? [L.p05 - idxRet, L.p95 - idxRet]
      : mg.length ? [Math.min(...mg), Math.max(...mg)] : null;
  const lucky = L && L.p95 != null ? raw.filter(p => (p.ret || 0) > L.p95!).length : null;
  const last = A.meta.updated;
  const active = new Set(P.filter(p => p.type !== "index" && p.type !== "equal" && p.log.some(l => l.d === last && (l.k === "buy" || l.k === "sell"))).map(p => p.id));
  const order = [...agents, ...(index ? [index] : []), ...(equal ? [equal] : []), ...monkeys];
  const dates = A.meta.dates, lastI = Math.max(0, dates.length - 1);
  const off = (p: Participant) => Math.max(0, dates.indexOf(p.from));
  const valueAt = (p: Participant, i: number) => { const k = i - off(p); return k < 0 ? p.s[0] : p.s[Math.min(k, p.s.length - 1)]; };
  const retAt = (p: Participant, i: number) => valueAt(p, i) / (p.s[0] || 1) - 1;
  // gap to the index over the participant's own life (newborns are compared from their birth, not from day zero)
  const gapAt = (p: Participant, i: number) => {
    if (p.type === "index") return 0;
    if (!index) return retAt(p, i);
    const o = off(p), base = valueAt(index, o) || 1;
    return retAt(p, i) - (valueAt(index, Math.max(i, o)) / base - 1);
  };
  const luckAt = (i: number): [number, number] | null => {
    if (i === 0) return null;
    const b = L?.s?.[i];
    if (b && index) return [b[0] - retAt(index, i), b[1] - retAt(index, i)];
    const g = monkeys.map(p => gapAt(p, i));
    return g.length ? [Math.min(...g), Math.max(...g)] : null;
  };
  const rankCache = new Map<number, { agents: Participant[]; rank: Record<string, number> }>();
  const rankAt = (i: number) => {
    if (i === lastI) return { agents, rank };
    if (!rankCache.has(i)) {
      const a = raw.slice().sort((x, y) => (gapAt(y, i) - gapAt(x, i)) || x.name.localeCompare(y.name));
      const r: Record<string, number> = {}; a.forEach((p, k) => r[p.id] = k + 1);
      rankCache.set(i, { agents: a, rank: r });
    }
    return rankCache.get(i)!;
  };
  const activeAt = (i: number) => i === lastI ? active : new Set(A.fillsByDay?.[dates[i]] || []);
  let span = 0.04;
  for (let i = 0; i <= lastI; i++) {
    for (const p of P) span = Math.max(span, Math.abs(gapAt(p, i)));
    const b = luckAt(i); if (b) span = Math.max(span, Math.abs(b[0]), Math.abs(b[1]));
  }
  return { A, byId, agents, monkeys, index, equal, order, species: Object.keys(A.species), scored, moved, luck,
    luckN: L?.n || monkeys.length, lucky, active, rank, gap, last: lastI, retAt, gapAt, valueAt, luckAt, rankAt, activeAt, span,
    medianAt: (i: number) => { const v = raw.map(p => valueAt(p, i)).sort((a, b) => a - b); return v.length ? v[Math.floor(v.length / 2)] : A.meta.capital; } };
}

// ---------- formatting (en-GB, tabular) ----------
export const nf = (x: number | null | undefined, d = 0) =>
  x == null || !isFinite(x) ? "—" : x.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
export const eur = (x: number | null | undefined, d = 0) => x == null ? "—" : (x < 0 ? "−€" : "€") + nf(Math.abs(x), d);
export const pct = (x: number | null | undefined, d = 1, sign = true) =>
  x == null ? "—" : (sign && x > 0 ? "+" : x < 0 ? "−" : "") + nf(Math.abs(x * 100), d) + "%";
export const tone = (x: number | null | undefined) => x == null || Math.abs(x) < 5e-5 ? "" : x > 0 ? "up" : "down";
export const day = (d?: string | null) => d ? new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }) : "—";
export const dayY = (d?: string | null) => d ? new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "—";
export const label = (p: Participant) =>
  p.type === "index" ? "S&P 500" : p.type === "equal" ? "Equal weight" : p.type === "monkey" ? "Monkey " + ((p.name.match(/\d+/) || [""])[0]) : p.name;
export const tick = (t: string) => t.replace("^SP500TR", "S&P TR");

// ---------- colours (one hue per species, everywhere) ----------
export const SPECIES_COLOR: Record<string, string> = {
  arrow: "#ff8a3d", wave: "#b07cff", rock: "#2fe0a8", echo: "#ffd84a", plumb: "#4da3ff", mirror: "#ff5fa2", compass: "#7ff0ff",
};
export const COLOR = { monkey: "#6f7686", equal: "#ffffff", index: "#38c6ff", up: "#3ee08f", down: "#ff6b6b", gold: "#ffd34d", silver: "#dfe6f0", bronze: "#d99a5b", luck: "#a9b1c2" };
export const colorOf = (p: Participant) => p.type === "agent" ? (SPECIES_COLOR[p.sp || ""] || "#9aa4b8") : p.type === "monkey" ? COLOR.monkey : p.type === "equal" ? COLOR.equal : COLOR.index;

export const sigLabel = (A: Arena, k: string) => A.meta.signals?.[k] || k;

// ---------- Verify: rebuild the readings text, check its SHA-256, recompute the decision ----------
export async function sha256(text: string) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
}
export function readingsText(sig: Shard["sig"]) {
  return Object.keys(sig.z).sort().map(t => t + "|" + sig.z[t].map(v => v.toFixed(6)).join(",") + "\n").join("") + "cols|" + sig.cols.join(",") + "\n";
}
export function scoreAll(sh: Shard, w: Record<string, number>) {
  const cols = sh.sig.cols, skip = new Set([...sh.excluded, ...sh.delisted]);
  const sc: Record<string, number> = {};
  for (const t of Object.keys(sh.sig.z)) {
    if (skip.has(t)) continue;
    let s = 0; sh.sig.z[t].forEach((v, k) => { s += v * (w[cols[k]] || 0) / 100; });
    sc[t] = Math.round(s * 1e4) / 1e4;
  }
  const ranking = Object.keys(sc).sort((a, b) => (sc[b] - sc[a]) || (a < b ? -1 : 1));
  return { sc, ranking };
}
export interface Verdict { hashOk: boolean; hash: string; scoreOk: boolean; rankOk: boolean; score: number | null; rank: number | null; of: number; terms: { s: string; z: number; w: number; term: number; raw: number | null }[] }
export async function verify(sh: Shard, w: Record<string, number>, t: string, r: Reason): Promise<Verdict> {
  const hash = await sha256(readingsText(sh.sig));
  const { sc, ranking } = scoreAll(sh, w);
  const score = sc[t] ?? null, rank = score == null ? null : ranking.indexOf(t) + 1;
  const k = sh.sig.cols;
  const terms = (sh.sig.z[t] || []).map((z, i) => ({ s: k[i], z, w: w[k[i]] || 0, term: z * (w[k[i]] || 0) / 100, raw: sh.sig.raw[t]?.[i] ?? null }))
    .filter(x => x.w).sort((a, b) => Math.abs(b.term) - Math.abs(a.term));
  return {
    hashOk: hash === sh.sig.sha256, hash, score, rank, of: ranking.length, terms,
    scoreOk: score != null && r.score != null && Math.abs(score - r.score) <= 1.5e-4,
    rankOk: rank != null && rank === r.rank,
  };
}
