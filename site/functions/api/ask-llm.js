// Model relay for the Ask exam (behind the same GitHub login as the whole site; the login gate runs first).
// The exam runner (site/scripts/ask-exam.mjs --remote, run by .github/workflows/ask-exam.yml) runs the whole
// Ask system on the frozen snapshot and only sends the model call here, so the exam uses the same free
// Workers AI binding as the live Ask, with no extra key. Only the candidate models, with capped sizes.
const ALLOWED = new Set(["@cf/openai/gpt-oss-120b", "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/meta/llama-3.1-8b-instruct-fast"]);
const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });

export async function onRequestPost({ request, env }) {
  if (!env.AI) return json({ error: "ai-not-configured" }, 503);
  let b; try { b = await request.json(); } catch { return json({ error: "bad-request" }, 400); }
  const model = String(b.model || ""), body = b.body || {};
  if (!ALLOWED.has(model)) return json({ error: "model-not-allowed" }, 400);
  if (!Array.isArray(body.messages) || JSON.stringify(body.messages).length > 60000) return json({ error: "bad-messages" }, 400);
  const input = { messages: body.messages.map(m => ({ role: String(m.role), content: String(m.content) })), max_tokens: Math.min(1500, Number(body.max_tokens) || 900), temperature: Math.min(1, Number(body.temperature) || 0) };
  if (body.reasoning) input.reasoning = { effort: "low" };
  if (body.response_format) input.response_format = { type: "json_object" };
  try { return json({ result: await env.AI.run(model, input) }); }
  catch (e) {
    const msg = String(e?.message || e);
    return json({ error: msg.slice(0, 300) }, /limit|quota|neuron|exceed|4006|429/i.test(msg) ? 429 : 502);
  }
}
