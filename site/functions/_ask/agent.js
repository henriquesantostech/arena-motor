// Ask v2: the analyst. Understand the question, call our tools, let the model phrase the answer from the
// facts only (one call, at most one more for extra tools), check it, and return one card.
// Without AI (free allowance used up, or no model) the same tools give a plain answer ("fast" mode).
import { prepare, dayName } from "./store.js";
import { understand } from "./understand.js";
import { runTool, getAgent, ranking } from "./tools.js";
import { SYSTEM, userMessage, detectLang, isExpert } from "./prompt.js";
import { chat, parseJson, QuotaError } from "./models.js";
import { clean, hasAdvice, groundSet, ungrounded } from "./guard.js";
import { UNIVERSE } from "./universe.js";

const VIEWS = ["today", "race", "story", "detail", "evidence", "journal", "evolution", "world", "network", "people", "lab"];
const KINDS = ["answer", "clarify", "unknown", "refuse"];
const words = s => String(s || "").trim().split(/\s+/).filter(Boolean).length;

function describe(v) {
  switch (v.type) {
    case "stat": return `big number ${v.label}`;
    case "line": return `chart over time: ${v.series.map(s => s.name).join(" vs ")}`;
    case "tiles": return `tiles of ${v.items.length} holdings`;
    case "bars": return `bars: ${v.items.slice(0, 4).map(i => i.name).join(", ")}${v.items.length > 4 ? "..." : ""}`;
    case "drivers": return "the reasons behind a decision";
    case "luck": return `where ${v.label} sits among 1,000 random monkeys`;
    case "list": return `list of ${v.items.length} items`;
    default: return v.type;
  }
}

// Merge tool results into one keyed pack the model can refer to (v1.., s1.., g1..).
function pack(results) {
  const P = { facts: [], visuals: {}, sources: {}, show: {}, follow: [], leads: [], focus: {} };
  let v = 0, s = 0, g = 0;
  for (const r of results) {
    if (!r) continue;
    P.leads.push(r.lead);
    P.facts.push(...r.facts);
    for (const x of Object.values(r.visuals || {})) P.visuals["v" + ++v] = { ...x, desc: describe(x) };
    for (const x of Object.values(r.sources || {})) if (!Object.values(P.sources).some(y => y.label === x.label)) P.sources["s" + ++s] = x;
    for (const x of Object.values(r.show || {})) if (!Object.values(P.show).some(y => y.label === x.label)) P.show["g" + ++g] = x;
    P.follow.push(...(r.follow || []));
    P.focus = { ...r.focus, ...P.focus };
  }
  return P;
}

function validGo(go, C) {
  if (!go || typeof go !== "object") return null;
  const o = {};
  if (go.agent && C.byId[go.agent]) o.agent = go.agent;
  if (go.company && UNIVERSE.some(r => r[0] === go.company)) o.company = go.company;
  if (go.date && C.dates.includes(go.date)) o.date = go.date;
  if (go.view && VIEWS.includes(go.view)) o.view = go.view;
  return Object.keys(o).length ? o : null;
}
const strip = v => { if (!v) return null; const { desc, ...x } = v; return x; };

function card(C, base) {
  const c = { v: 2, kind: base.kind, say: clean(base.say), more: (base.more || []).map(clean).filter(Boolean).slice(0, 3).map(m => /[.!?:)]$/.test(m) ? m : m + "."), visual: strip(base.visual),
    show: (base.show || []).map(x => ({ label: clean(x.label), go: validGo(x.go, C) })).filter(x => x.go).slice(0, 3),
    sources: (base.sources || []).map(x => ({ ...x, label: clean(x.label), go: validGo(x.go, C) || undefined })).filter(x => x.label && (x.go || x.url)).slice(0, 4),
    follow: [...new Set((base.follow || []).map(clean).filter(Boolean))].slice(0, 3), options: (base.options || []).map(clean).filter(Boolean).slice(0, 4),
    focus: base.focus || {}, asOf: C.day, mode: base.mode, model: base.model || null };
  if (!c.options.length) delete c.options;
  return c;
}

// Plain answer from the tools alone (no AI).
function fastCard(C, P, U, kind = "answer", note) {
  const say = P.leads[0] || "I could not find that in the archive.";
  const vis = Object.values(P.visuals)[0] || null;
  return card(C, { kind: P.leads.length ? kind : "unknown", say, more: [note, ...P.leads.slice(1, 3)].filter(Boolean), visual: vis, show: Object.values(P.show).slice(0, 2),
    sources: Object.values(P.sources).slice(0, 3), follow: P.follow, focus: P.focus, mode: "fast" });
}

function notesFor(U, C) {
  const n = [];
  if (U.ghost.length && !U.agents.length) n.push(`No participant called ${U.ghost.join(", ")} exists. Participants are agents Arrow-01..04, Wave-01..04, Rock-01..04, Echo-01..04, Plumb-01..04, Monkey-01..10, the S&P 500 and the equal-weight benchmark.`);
  if (U.focusUsed.agent) n.push(`"it/they" refers to ${C.byId[U.agents[0]]?.name} (from the conversation).`);
  if (U.focusUsed.company) n.push(`"it" refers to the company ${U.companies[0]} (from the conversation).`);
  if (U.advice) n.push("The person is asking for investment advice: refuse (kind refuse), then give one useful fact.");
  if (U.vague) n.push("The question has no clear subject and the conversation does not give one: ask which one (kind clarify).");
  if (U.dates.some(d => d > C.day)) n.push(`Asked about a day after ${dayName(C.day)}: we cannot know it yet.`);
  if ((q.match(/\b(19|20)\d\d\b/g) || []).some(y => +y < +C.dates[0].slice(0, 4))) n.push(`The arena started on ${dayName(C.dates[0])}: there is no record for that year. Say so (kind unknown) and give the start date.`);
  if (U.dates.some(d => d < C.dates[0])) n.push(`The arena started on ${dayName(C.dates[0])}; nothing exists before that.`);
  return n;
}

export async function answer(req, { store, env, models = [], mode = "ai", budget }) {
  const C = await prepare(store, req.asOf || null);
  const q = String(req.q || "").slice(0, 600).trim();
  const history = Array.isArray(req.history) ? req.history.slice(-4) : [];
  const U = understand(q, C, history, req.screen || {});

  // Screen commands ("show me Echo-01", "open the journal of 17 November"): no AI needed.
  if (U.command && U.go && !/\?\s*$/.test(q)) {
    const results = await Promise.all(U.plan.filter(p => ["get_agent", "company_story", "market_summary"].includes(p.tool)).slice(0, 1).map(p => runTool(C, p.tool, p.args)));
    const P = pack(results);
    const lead = U.go.agent ? `Here is ${C.byId[U.go.agent].name}${U.go.view === "detail" ? "'s holdings" : ""}.` : U.go.view === "journal" ? `Opening the journal${U.go.date ? " of " + dayName(U.go.date) : ""}.` : `Opening ${U.go.view || "the arena"}${U.go.date ? " on " + dayName(U.go.date) : ""}.`;
    const vis = U.go.view === "detail" ? Object.values(P.visuals).find(v => v.type === "tiles") : Object.values(P.visuals)[0];
    return card(C, { kind: "command", say: lead, more: P.leads.slice(0, 1), visual: vis || null, show: [{ label: lead.replace(/\.$/, ""), go: U.go }], sources: Object.values(P.sources).slice(0, 2), follow: P.follow, focus: { ...P.focus, ...(U.go.agent ? { agent: U.go.agent } : {}) }, mode: "fast" });
  }

  let results = await Promise.all(U.plan.map(p => runTool(C, p.tool, p.args)));
  let P = pack(results);
  const notes = notesFor(U, C);

  if (mode !== "ai" || !models.length) {
    if (U.advice) return card(C, { kind: "refuse", say: "I can't give investment advice: the agents trade simulated money, and a few days of results say very little.", more: P.leads.slice(0, 1), follow: ["Who is winning?", "What is the luck band?"], sources: Object.values(P.sources).slice(0, 2), mode: "fast" });
    if (U.vague) return card(C, { kind: "clarify", say: "Which one do you mean?", options: [C.ranked[0]?.name, "The market", "All the agents"].filter(Boolean), mode: "fast" });
    return fastCard(C, P, U, "answer", mode === "limit" ? "Today's free AI allowance is used up, so this is the plain answer from our data." : null);
  }

  const lang = detectLang(q, req.lang);
  const reader = isExpert(q) ? "expert" : "lay";
  const trace = { model: null, calls: 0, tokens: { in: 0, out: 0 }, ms: 0 };
  const build = () => userMessage({ q, lang, reader, asOf: dayName(C.day), latest: C.latest, history, notes, facts: P.facts, visuals: P.visuals, sources: P.sources, show: P.show });
  let messages = [{ role: "system", content: SYSTEM }, { role: "user", content: build() }];

  let out = null, lastErr = null;
  for (const id of models) {
    try {
      out = null;
      for (let round = 0; round < 3 && !out; round++) {
        if (budget && !budget.take()) throw new QuotaError("own daily limit");
        const r = await chat(id, messages, env);
        trace.model = id; trace.calls++; trace.tokens.in += r.usage.in; trace.tokens.out += r.usage.out; trace.ms += r.ms;
        const j = parseJson(r.text);
        if (!j) { if (round === 0) { messages = [...messages, { role: "assistant", content: String(r.text).slice(0, 400) }, { role: "user", content: "Reply with the JSON object only." }]; continue; } break; }
        if (Array.isArray(j.need) && j.need.length && round === 0) {
          const extra = await Promise.all(j.need.slice(0, 3).map(n => runTool(C, String(n.tool || ""), n.args || {}).catch(() => null)));
          if (extra.some(Boolean)) { results = [...results, ...extra]; P = pack(results); }
          messages = [{ role: "system", content: SYSTEM }, { role: "user", content: build() + "\n(These are all the facts available now; answer with the JSON card.)" }];
          continue;
        }
        // numbers must come from the facts
        const S = groundSet([...P.facts, q, ...history.map(h => h.say || "")]);
        const bad = ungrounded([j.say, ...(j.more || [])].join(" "), S);
        if (bad.length && round < 2) {
          messages = [...messages, { role: "assistant", content: JSON.stringify(j).slice(0, 1500) }, { role: "user", content: `These numbers are not in the FACTS: ${bad.slice(0, 5).join(", ")}. Rewrite using only numbers from the FACTS. JSON only.` }];
          continue;
        }
        if (bad.length) { j.more = (j.more || []).filter(m => !ungrounded(m, S).length); if (ungrounded(j.say, S).length) j.say = P.leads[0] || j.say; }
        out = j;
      }
      if (out) break;
    } catch (e) { lastErr = e; if (!(e instanceof QuotaError) && !/no (AI binding|Groq key)/.test(String(e.message))) { /* model error: try the next one */ } }
  }
  if (!out) {
    const limited = lastErr instanceof QuotaError;
    const c = U.advice ? card(C, { kind: "refuse", say: "I can't give investment advice: the agents trade simulated money.", mode: "fast" })
      : fastCard(C, P, U, "answer", limited ? "Today's free AI allowance is used up, so this is the plain answer from our data." : "The AI is unavailable right now, so this is the plain answer from our data.");
    if (limited) c.kind = c.kind === "answer" ? "limit" : c.kind;
    c.trace = trace;
    return c;
  }

  let kind = KINDS.includes(out.kind) ? out.kind : "answer";
  if (U.vague && kind !== "clarify" && !String(out.say || "").trim()) { kind = "clarify"; out.say = "Which one do you mean?"; out.options = [C.ranked[0]?.name, "The market", "All the agents"].filter(Boolean); }
  if (!String(out.say || "").trim()) out.say = P.leads[0] || "I could not find that in the archive.";
  let say = String(out.say || ""), more = Array.isArray(out.more) ? out.more.map(String) : [];
  if (hasAdvice([say, ...more].join(" "))) { say = "I can't give investment advice: the agents trade simulated money, and nothing here says what anyone should buy or sell."; more = P.leads.slice(0, 1); }
  const pick = (keys, map) => (Array.isArray(keys) ? keys : [keys]).map(k => map[String(k)]).filter(Boolean);
  let visual = out.visual && P.visuals[String(out.visual)] || null;
  if (!visual && kind === "answer" && !U.advice) visual = Object.values(P.visuals)[0] || null;
  let sources = pick(out.sources, P.sources);
  if (!sources.length && (kind === "answer")) sources = Object.values(P.sources).slice(0, 2);
  let show = pick(out.show, P.show);
  if (!show.length && kind === "answer") show = Object.values(P.show).slice(0, 1);
  const follow = Array.isArray(out.follow) && out.follow.length ? out.follow.map(String) : P.follow;
  const c = card(C, { kind, say, more, visual: kind === "answer" || kind === "unknown" ? visual : null, show, sources: kind === "clarify" ? [] : sources, follow, options: kind === "clarify" ? out.options : [], focus: P.focus, mode: "ai", model: trace.model });
  if (words(c.say) > 45) c.say = c.say.split(/(?<=[.!?])\s/)[0];
  c.trace = trace;
  return c;
}
