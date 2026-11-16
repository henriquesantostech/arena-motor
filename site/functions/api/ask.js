// ASK copilot, server side (Pages Function behind the same GitHub login as the whole site).
// Grounded: the model sees only the passages the browser retrieved from our archive (as known at the
// selected day), must cite them by id, and may not give investment advice. Zero cost: Workers AI free
// allocation through the AI binding; when that is used up or unavailable, the browser falls back to
// "search only" (it still shows the passages).
const MODELS = ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/meta/llama-3.1-8b-instruct-fast"];
const MAX_Q = 600, MAX_P = 12, MAX_T = 900;

const SYSTEM = `You are ASK, the copilot of "Arena of Agents", a research experiment where software agents trade SIMULATED money on the S&P 100.
Rules you must follow:
- Use ONLY the passages given. Each passage starts with its id in square brackets. If they do not contain the answer, say you do not know from the archive.
- After every sentence that states a fact, put the id of the passage it comes from in square brackets, exactly as given, e.g. "Rock-02 leads the ranking [standings]." Never invent numbers, names or dates.
- Everything is as known on the "as of" date; never mention later events.
- Never tell anyone to buy, sell or hold anything and never give personal investment advice. If asked, say plainly that you cannot give investment advice, then summarise what the passages show and remind that the agents are simulated.
- Answer in the SAME LANGUAGE as the question, in at most 120 words, plain and direct.
- If the user asks to see something (an agent, a day, the journal, the evolution tree), add interface actions: {"type":"open","id":"<participant id>"}, {"type":"date","d":"YYYY-MM-DD"}, {"type":"lens","lens":"today|arena|evolution|journal"}.
Reply with JSON only: {"answer": string with [id] markers, "actions": [...]}`;

const hits = new Map();   // light per-isolate rate guard (the free allocation is the real cap)

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });
}

export async function onRequestPost({ request, env }) {
  if (!env.AI) return json({ error: "ai-not-configured" }, 503);
  let body;
  try { body = await request.json(); } catch { return json({ error: "bad-request" }, 400); }
  const q = String(body.q || "").slice(0, MAX_Q).trim();
  if (!q) return json({ error: "empty" }, 400);
  const passages = (Array.isArray(body.passages) ? body.passages : []).slice(0, MAX_P)
    .map(p => ({ id: String(p.id || "").slice(0, 120), d: p.d ? String(p.d).slice(0, 10) : null, title: String(p.title || "").slice(0, 160), text: String(p.text || "").slice(0, MAX_T) }))
    .filter(p => p.id);
  const ids = new Set(passages.map(p => p.id));
  const who = (request.headers.get("Cookie") || "").match(/arena_session=([^.;]+)/)?.[1] || "anon";
  const now = Date.now(), h = (hits.get(who) || []).filter(t => now - t < 3600e3);
  if (h.length >= 60) return json({ error: "rate" }, 429);
  hits.set(who, [...h, now]);

  const ctx = passages.map((p, i) => `[${p.id}] (${p.d || "undated"}) ${p.title}: ${p.text}`).join("\n");
  const user = `as of: ${String(body.asOf || "latest").slice(0, 10)}\n(reply in the language the question is written in)\nquestion: ${q}\n\npassages:\n${ctx || "(none)"}`;
  for (const model of MODELS) {
    try {
      const r = await env.AI.run(model, {
        messages: [{ role: "system", content: SYSTEM }, { role: "user", content: user }],
        max_tokens: 400, temperature: 0.2,
        response_format: { type: "json_object" },
      });
      const raw = typeof r?.response === "string" ? r.response : JSON.stringify(r?.response ?? "");
      let out;
      try { out = typeof r?.response === "object" ? r.response : JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1)); } catch { out = { answer: raw }; }
      let text = String(out.answer || "");
      const found = [...text.matchAll(/\[([^\[\]]{1,120})\]/g)].flatMap(m => m[1].split(/[,;]\s*/)).map(x => x.trim());
      const cite = [...new Set([...found, ...(Array.isArray(out.cite) ? out.cite.map(String) : [])])].filter(x => ids.has(x)).slice(0, 8);
      text = text.replace(/\s*\[([^\[\]]{1,120})\]/g, (m, inner) => inner.split(/[,;]\s*/).some(x => ids.has(x.trim())) ? "" : m).trim();
      const actions = (Array.isArray(out.actions) ? out.actions : []).filter(a => a && ["open", "date", "lens"].includes(a.type)).slice(0, 4);
      return json({ text: text.slice(0, 1500), cite, actions, model });
    } catch (e) {
      const msg = String(e && e.message || e);
      if (/limit|quota|neuron|429|exceed/i.test(msg)) return json({ error: "quota" }, 429);
      // try the next (smaller) model
    }
  }
  return json({ error: "unavailable" }, 503);
}
