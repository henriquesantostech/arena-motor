// Ask exam runner: puts every frozen question through the whole Ask v2 system and grades it.
//   node site/scripts/ask-exam.mjs <exam folder> [--model id[,id]] [--fast] [--out report.json] [--only L01,E04]
// Exam folder = the private archive's ask/exam_v1 (exam.json, questions.jsonl, data/).
// Models: Workers AI over its REST API (CF_ACCOUNT_ID + CF_AI_TOKEN) or Groq (GROQ_API_KEY). Keys only from the environment.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { makeStore } from "../functions/_ask/store.js";
import { answer } from "../functions/_ask/agent.js";

const args = process.argv.slice(2);
const dir = args[0];
const opt = k => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const fast = args.includes("--fast");
const models = (opt("--model") || "").split(",").filter(Boolean);
const only = (opt("--only") || "").split(",").filter(Boolean);
const E = JSON.parse(readFileSync(join(dir, "exam.json"), "utf8"));
let Q = readFileSync(join(dir, "questions.jsonl"), "utf8").split("\n").filter(Boolean).map(l => JSON.parse(l));
if (only.length) Q = Q.filter(x => only.includes(x.id));
const store = makeStore(p => { const f = join(dir, "data", p); return existsSync(f) ? JSON.parse(readFileSync(f, "utf8")) : null; });

const env = { GROQ_API_KEY: process.env.GROQ_API_KEY };
if (process.env.CF_ACCOUNT_ID && process.env.CF_AI_TOKEN) env.AI = {
  run: async (model, body) => {
    const r = await fetch(`https://api.cloudflare.com/client/v4/accounts/${process.env.CF_ACCOUNT_ID}/ai/run/${model}`, { method: "POST", headers: { Authorization: `Bearer ${process.env.CF_AI_TOKEN}`, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.success === false) throw new Error(`${r.status} ${(j.errors || []).map(e => e.code + " " + e.message).join("; ")}`);
    return j.result;
  },
};

// ---------- grading ----------
const G = E.global, re = s => new RegExp(s, "i");
const textOf = c => [c.say, ...(c.more || [])].join(" ");
const allText = c => [c.say, ...(c.more || []), ...(c.follow || []), ...(c.options || []), ...(c.show || []).map(x => x.label), ...(c.sources || []).map(x => x.label)].join(" \n ");
function nums(t) { return [...t.matchAll(/(?<![\w.])-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:[.,]\d+)?\s*k?/gi)].flatMap(m => { let s = m[0].trim().toLowerCase(), k = 1; if (s.endsWith("k")) { k = 1000; s = s.slice(0, -1); } const o = []; if (/^-?\d+,\d{1,2}$/.test(s)) o.push(parseFloat(s.replace(",", "."))); o.push(parseFloat(s.replace(/,/g, ""))); return o.map(x => Math.abs(x * k)); }); }
function check(ch, t) {
  if (ch.any) return ch.any.some(c => check(c, t));
  if (ch.text) return ch.text.some(x => t.toLowerCase().includes(x.toLowerCase()));
  if (ch.num) { const ns = nums(t); return ch.num.some(v => ns.some(n => Math.abs(n - Math.abs(v)) <= (ch.tol ?? 0) + 1e-9)); }
  if (ch.says) return re(G.says[ch.says]).test(t);
  return false;
}
const LANG = { pt: /\b(o|a|os|as|não|está|é|do|da|que|em|de|mas|perdeu|mercado|dinheiro)\b/gi, es: /\b(el|la|los|las|no|está|es|del|que|en|de|pero|compró|mercado|dinero|empresas)\b/gi };
function fk(t) {   // Flesch-Kincaid grade (English)
  const s = Math.max(1, (t.match(/[.!?](\s|$)/g) || []).length), w = t.split(/\s+/).filter(Boolean);
  const syl = w.reduce((a, x) => a + Math.max(1, (x.toLowerCase().replace(/[^a-z]/g, "").replace(/e$/, "").match(/[aeiouy]+/g) || []).length), 0);
  return 0.39 * (w.length / s) + 11.8 * (syl / Math.max(1, w.length)) - 15.59;
}
const TICKERS = JSON.parse(readFileSync(new URL("../functions/_ask/universe.js", import.meta.url), "utf8").match(/UNIVERSE = (\[.*\]);/s)[1]).map(r => r[0]).filter(t => t.length >= 2);
function grade(it, c) {
  const t = textOf(c), x = it.expect, why = [];
  const kindOk = x.kind.includes(c.kind === "command" ? "command" : c.kind === "limit" ? "answer" : c.kind);
  if (!kindOk) why.push(`kind ${c.kind}`);
  (x.all || []).forEach((ch, i) => { if (!check(ch, t)) why.push(`check ${i + 1} ${JSON.stringify(ch).slice(0, 60)}`); });
  (x.none || []).forEach(p => { if (re(p).test(t)) why.push(`forbidden /${p}/`); });
  if (x.go) { const gos = [...(c.show || []), ...(c.sources || [])].map(s => s.go || {}); if (!gos.some(g => Object.entries(x.go).every(([k, v]) => g[k] === v))) why.push("no go " + JSON.stringify(x.go)); }
  if (it.lang !== "en" && (t.match(LANG[it.lang]) || []).length < 3) why.push("language");
  const correct = !why.length;
  const cw = [], A = allText(c);
  if (G.raw_id.some(p => re(p).test(A))) cw.push("raw id");
  const lay = it.level === "lay";
  if ((c.say || "").split(/\s+/).length > (lay ? 35 : 45)) cw.push("say too long");
  if (t.split(/\s+/).length > (lay ? 120 : 180)) cw.push("too long");
  if (lay && it.lang === "en" && fk(t) > 10) cw.push("grade " + fk(t).toFixed(1));
  if (lay && G.jargon.some(p => re(p).test(t) && !re(p).test(it.q))) cw.push("jargon");
  if (lay) for (const tk of TICKERS) if (new RegExp(`(^|[^(A-Za-z])${tk.replace(".", "\\.")}(?![A-Za-z)])`).test(t)) { cw.push("bare ticker " + tk); break; }
  if (x.visual && !(c.visual && x.visual.includes(c.visual.type))) cw.push("visual " + (c.visual?.type || "none"));
  const ew = [];
  if (c.kind === "answer" || c.kind === "limit") {
    if (!c.sources?.length) ew.push("no source");
    if ((c.sources || []).some(s => !s.label || (!s.go && !s.url))) ew.push("bad source");
    if (x.sources && !(c.sources || []).some(s => x.sources.includes(s.kind))) ew.push("source kind");
  }
  const advice = G.advice.some(p => re(p).test(A));
  return { correct, clarity: !cw.length, evidence: !ew.length, noAdvice: !advice, rawId: G.raw_id.some(p => re(p).test(A)), why: [...why, ...cw.map(w => "clarity: " + w), ...ew.map(w => "evidence: " + w), ...(advice ? ["ADVICE"] : [])] };
}

// ---------- run ----------
const rows = [];
for (const it of Q) {
  const t0 = Date.now();
  let c;
  try { c = await answer({ q: it.q, asOf: it.asOf || null, history: it.history || [], lang: it.lang }, { store, env, models, mode: fast || !models.length ? "fast" : "ai" }); }
  catch (e) { c = { kind: "error", say: String(e.message || e), more: [], sources: [], show: [], follow: [] }; }
  const g = grade(it, c);
  rows.push({ id: it.id, level: it.level, ms: Date.now() - t0, tokens: c.trace?.tokens, model: c.model, ...g, card: c });
  console.log(`${it.id} ${g.correct ? "OK " : "-- "}${g.clarity ? "c" : "."}${g.evidence ? "e" : "."}${g.noAdvice ? "" : " ADVICE"} ${((Date.now() - t0) / 1000).toFixed(1)}s ${g.why.join(" | ").slice(0, 160)}`);
}
const share = (f, xs = rows) => xs.filter(f).length / Math.max(1, xs.length);
const lat = rows.map(r => r.ms / 1000).sort((a, b) => a - b), q = p => lat[Math.min(lat.length - 1, Math.floor(p * lat.length))];
const tok = rows.filter(r => r.tokens).map(r => r.tokens.in + r.tokens.out).sort((a, b) => a - b);
const S = {
  n: rows.length, correctness: share(r => r.correct), lay: share(r => r.correct, rows.filter(r => r.level === "lay")), expert: share(r => r.correct, rows.filter(r => r.level === "expert")),
  clarity: share(r => r.clarity), evidence: share(r => r.evidence), no_advice: share(r => r.noAdvice), no_raw_ids: share(r => !r.rawId),
  latency_p50_s: q(0.5), latency_p95_s: q(0.95), tokens_median: tok.length ? tok[Math.floor(tok.length / 2)] : 0,
};
const P = E.pass;
S.pass = S.correctness >= P.correctness_min && S.lay >= P.correctness_min_per_level && S.expert >= P.correctness_min_per_level && S.clarity >= P.clarity_min && S.evidence >= P.evidence_min
  && S.no_advice >= P.no_advice && S.no_raw_ids >= P.no_raw_ids && S.latency_p50_s <= P.latency_p50_max_s && S.latency_p95_s <= P.latency_p95_max_s;
console.log(JSON.stringify({ models: models.length ? models : ["fast (no AI)"], ...S }, null, 1));
if (opt("--out")) writeFileSync(opt("--out"), JSON.stringify({ exam: E.version, models, at: new Date().toISOString(), summary: S, rows }, null, 1));
