// ASK copilot, browser side: retrieval over the nightly corpus (BM25, as known at the selected day),
// interface commands ("show Arrow-03 in March"), and the call to /api/ask (behind the same login).
import type { Model } from "./data";

export interface Passage { id: string; d: string | null; k: string; title: string; text: string; cites?: string[]; ref?: { open?: string; date?: string; lens?: string; species?: string } }
export interface Action { type: "open" | "date" | "lens" | "close"; id?: string; d?: string; lens?: string }
export interface Answer { text: string; cites: Passage[]; actions: Action[]; mode: "ai" | "search" | "command"; note?: string }

let corpusP: Promise<Passage[]> | null = null;
export function loadCorpus() {
  corpusP ||= fetch("./data/corpus.json").then(r => r.ok ? r.json() : { passages: [] }).then(j => j.passages as Passage[]);
  return corpusP;
}

const STOP = new Set("a an and are as at be by did do does for from has have how i in is it its me of on or show tell than that the this to was were what when where which who why will with you your".split(" "));
const tok = (s: string) => s.toLowerCase().normalize("NFKD").replace(/[^\p{L}\p{N}&^\-.%]+/gu, " ").split(/\s+/).map(t => t.replace(/^[-.]+|[-.]+$/g, "")).filter(t => t && !STOP.has(t));

type Index = { docs: Passage[]; tf: Map<string, number>[]; len: number[]; df: Map<string, number>; avg: number };
let indexP: Promise<Index> | null = null;
function index(): Promise<Index> {
  indexP ||= loadCorpus().then(docs => {
    const tf: Map<string, number>[] = [], len: number[] = [], df = new Map<string, number>();
    for (const d of docs) {
      const m = new Map<string, number>(), t = tok(d.title + " " + d.title + " " + d.text);
      t.forEach(w => m.set(w, (m.get(w) || 0) + 1));
      m.forEach((_, w) => df.set(w, (df.get(w) || 0) + 1));
      tf.push(m); len.push(t.length);
    }
    return { docs, tf, len, df, avg: len.reduce((a, b) => a + b, 0) / Math.max(1, len.length) };
  });
  return indexP;
}

export async function search(q: string, asOf: string | null, k = 10): Promise<Passage[]> {
  const I = await index(), terms = tok(q), N = I.docs.length;
  const scored: [number, number][] = [];
  I.docs.forEach((d, i) => {
    if (asOf && d.d && d.d > asOf) return;   // as known then: nothing from after the selected day
    let s = 0;
    for (const t of terms) {
      const f = I.tf[i].get(t); if (!f) continue;
      const idf = Math.log(1 + (N - (I.df.get(t) || 0) + .5) / ((I.df.get(t) || 0) + .5));
      s += idf * f * 2.2 / (f + 1.2 * (.25 + .75 * I.len[i] / I.avg));
    }
    if (s > 0) scored.push([s, i]);
  });
  const top = scored.sort((a, b) => b[0] - a[0]).slice(0, k - 2).map(([, i]) => I.docs[i]);
  // always give the model the rules of the game and the current standings (as of the selected day)
  for (const id of ["standings", "about"]) {
    const d = I.docs.find(x => x.id === id);
    if (d && !top.includes(d) && !(asOf && d.d && d.d > asOf)) top.push(d);
  }
  return top;
}

// ---------- interface commands, understood without any AI ----------
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
export function parseCommand(q: string, M: Model): Action[] {
  const s = q.toLowerCase(), acts: Action[] = [], dates = M.A.meta.dates;
  const verb = /\b(show|open|go|take me|display|replay|jump|view|see)\b/.test(s);
  const p = M.order.find(x => new RegExp(`\\b${x.name.toLowerCase().replace(/[^a-z0-9]+/g, "[ -]?")}\\b`).test(s))
    || (/\bmonkey ?0?(\d+)/.test(s) ? M.monkeys.find(x => x.name.match(/\d+/)?.[0] === s.match(/\bmonkey ?0?(\d+)/)![1].padStart(2, "0")) : undefined)
    || (/\b(s&p|index|sp500|s and p)\b/.test(s) ? M.index : undefined)
    || (/\b(leader|best agent|first place|number one)\b/.test(s) ? M.agents[0] : undefined);
  // dates: ISO, "13 nov", "nov 13", a month, "first day", "yesterday", "today"
  let d: string | undefined;
  const iso = s.match(/\b(20\d\d-\d\d-\d\d)\b/);
  const dm = s.match(/\b(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b/) || s.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(\d{1,2})\b/);
  const mo = s.match(/\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b/);
  const pick = (pred: (x: string) => boolean, last = true) => { const c = dates.filter(pred); return c.length ? c[last ? c.length - 1 : 0] : undefined; };
  if (iso) d = pick(x => x <= iso[1]);
  else if (dm) {
    const [a, b] = /^\d/.test(dm[1]) ? [dm[1], dm[2]] : [dm[2], dm[1]];
    const mm = String(MONTHS.indexOf(b.slice(0, 3)) + 1).padStart(2, "0"), dd = a.padStart(2, "0");
    d = pick(x => x.slice(5) <= `${mm}-${dd}` && x.slice(5, 7) === mm) || pick(x => x.slice(5, 7) === mm, false);
  } else if (mo) { const mm = String(MONTHS.indexOf(mo[1].slice(0, 3)) + 1).padStart(2, "0"); d = pick(x => x.slice(5, 7) === mm); }
  else if (/\b(first day|day zero|beginning|start)\b/.test(s)) d = dates[0];
  else if (/\byesterday\b/.test(s)) d = dates[Math.max(0, dates.length - 2)];
  else if (/\b(today|latest|now|live)\b/.test(s) && verb) d = dates[dates.length - 1];
  const lens = s.match(/\b(journal|newspaper|evolution|tree|today|arena|lab|evidence|people|insiders?|congress)\b/)?.[1];
  if (lens && verb) acts.push({ type: "lens", lens: lens === "newspaper" ? "journal" : lens === "tree" ? "evolution" : lens === "evidence" ? "lab" : /insider|congress/.test(lens) ? "people" : lens });
  if (d && (verb || p)) { if (!lens) acts.push({ type: "lens", lens: "arena" }); acts.push({ type: "date", d }); }
  if (p && verb) acts.push({ type: "open", id: p.id });
  if (/\b(close|back|exit)\b/.test(s) && acts.length === 0 && s.split(" ").length < 4) acts.push({ type: "close" });
  return acts;
}

// ---------- the AI call (Pages Function /api/ask, Workers AI, free allocation) ----------
export async function ask(q: string, passages: Passage[], asOf: string | null, lang: string, signal?: AbortSignal):
  Promise<{ text: string; cite: string[]; actions?: Action[] } | { error: string }> {
  try {
    const r = await fetch("./api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal,
      body: JSON.stringify({ q, asOf, lang, passages: passages.map(p => ({ id: p.id, d: p.d, title: p.title, text: p.text })) }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.error) return { error: j.error || "unavailable" };
    return j;
  } catch { return { error: "offline" }; }
}
