// Ask v2 model providers (free plans only). Same chat messages for all; JSON answers.
//   workers-ai: the Pages AI binding (env.AI) - free daily allocation, no key in the code
//   groq:       Groq's free plan through its OpenAI-compatible API (env.GROQ_API_KEY, a Pages secret)
export const MODELS = {
  "gpt-oss-120b@groq": { provider: "groq", name: "openai/gpt-oss-120b", reasoning: true },
  "gpt-oss-120b@workers-ai": { provider: "workers-ai", name: "@cf/openai/gpt-oss-120b", reasoning: true },
  "llama-3.3-70b@workers-ai": { provider: "workers-ai", name: "@cf/meta/llama-3.3-70b-instruct-fp8-fast" },
  "llama-3.3-70b@groq": { provider: "groq", name: "llama-3.3-70b-versatile" },
};

export class QuotaError extends Error { constructor(m) { super(m); this.quota = true; } }
const isQuota = (status, msg) => status === 429 || /quota|limit|neuron|exceed|rate|capacity|4006|daily/i.test(String(msg || ""));

function pickText(r) {
  if (r == null) return "";
  if (typeof r === "string") return r;
  if (typeof r.response === "string") return r.response;
  if (r.response && typeof r.response === "object") return JSON.stringify(r.response);
  if (r.choices?.[0]?.message?.content) return r.choices[0].message.content;
  if (Array.isArray(r.output)) {   // Responses API shape
    for (const o of r.output) for (const c of o.content || []) if (c.type === "output_text" && c.text) return c.text;
  }
  if (typeof r.output_text === "string") return r.output_text;
  return "";
}
function usageOf(r) {
  const u = r?.usage || {};
  return { in: u.prompt_tokens ?? u.input_tokens ?? 0, out: u.completion_tokens ?? u.output_tokens ?? 0 };
}

export async function chat(id, messages, env, { maxTokens = 900, temperature = 0.1 } = {}) {
  const m = MODELS[id]; if (!m) throw new Error("unknown model " + id);
  const t0 = Date.now();
  if (m.provider === "workers-ai") {
    if (!env.AI) throw new Error("no AI binding");
    const body = { messages, max_tokens: maxTokens, temperature };
    if (m.reasoning) body.reasoning = { effort: "low" }; else body.response_format = { type: "json_object" };
    let r;
    try { r = await env.AI.run(m.name, body); } catch (e) { const msg = String(e?.message || e); if (isQuota(0, msg)) throw new QuotaError(msg); throw e; }
    return { text: pickText(r), usage: usageOf(r), ms: Date.now() - t0 };
  }
  if (m.provider === "groq") {
    if (!env.GROQ_API_KEY) throw new Error("no Groq key");
    const body = { model: m.name, messages, max_completion_tokens: maxTokens, temperature, response_format: { type: "json_object" } };
    if (m.reasoning) body.reasoning_effort = "low";
    const r = await fetch("https://api.groq.com/openai/v1/chat/completions", { method: "POST", headers: { Authorization: `Bearer ${env.GROQ_API_KEY}`, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { const msg = j?.error?.message || r.status; if (isQuota(r.status, msg)) throw new QuotaError(String(msg)); throw new Error(String(msg)); }
    return { text: pickText(j), usage: usageOf(j), ms: Date.now() - t0 };
  }
  throw new Error("unknown provider");
}

export function parseJson(text) {
  const s = String(text || "");
  const a = s.indexOf("{"), b = s.lastIndexOf("}");
  if (a < 0 || b <= a) return null;
  try { return JSON.parse(s.slice(a, b + 1)); } catch { return null; }
}
