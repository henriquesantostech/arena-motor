// Data model of the site. The engine writes data/arena.json (latest night) and data/days/<date>.json
// (one shard per night, for the Time Machine). Everything here is read-only and derived in the browser.

export type Kind = "agent" | "monkey" | "index" | "equal";

export interface Move { d: string; k: string; t: string; eur?: number | null; px?: number; n?: number; fee?: number; gain?: number | null; why?: string; ratio?: number }
export interface Holding { t: string; name: string; n: number; eur: number; w: number; gain: number | null; since: string }
export interface Dna { w: Record<string, number>; picks?: number; maxW?: number; review?: number; stop?: number | null; brake?: number }

export interface Participant {
  id: string; name: string; type: Kind; sp: string | null; born: string; parents?: string[] | null; copies?: string | null;
  value: number; ret: number; vsIdx: number | null; score: number | null; beatsMonkeys: number | null; merit: boolean | null;
  vol: number | null; mdd: number; fees: number; divs: number; turnover: number; hit: number | null; closed: number;
  tax: number; cash: number; days: number; s: number[]; from: string; dna: Dna | null; hold: Holding[];
  next: { k: string; t: string; eur?: number | null; all?: boolean; why?: string }[]; log: Move[];
  pctAll?: number | null; pctMirror?: number | null;
}

export interface Luck { n: number; date: string; p05: number | null; median: number | null; p95: number | null; best: number | null; s: ([number, number] | null)[] }

export interface Arena {
  meta: { mode: "trial" | "live"; dayZero: string; capital: number; rules: string; engine: string; updated: string | null; dates: string[] };
  species: Record<string, { label: string; family: string; about: string }>;
  p: Participant[];
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
}

export async function loadArena(): Promise<Arena> {
  const r = await fetch("./data/arena.json", { cache: "no-cache" });
  if (!r.ok) throw new Error("data " + r.status);
  return r.json();
}

export function buildModel(A: Arena): Model {
  const P = A.p;
  const byId = Object.fromEntries(P.map(p => [p.id, p]));
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
  return { A, byId, agents, monkeys, index, equal, order, species: Object.keys(A.species), scored, moved, luck,
    luckN: L?.n || monkeys.length, lucky, active, rank, gap };
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
