// Tests for the ASK function (with a fake Workers AI). Run: node --test site/tests/ask.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { onRequestPost } from "../functions/api/ask.js";

const req = body => new Request("https://arena.example/api/ask", { method: "POST", headers: { "Content-Type": "application/json", Cookie: "arena_session=alice.1.x" }, body: JSON.stringify(body) });
const P = [{ id: "p:arrow-01", d: "2026-11-13", title: "Arrow-01", text: "Arrow-01 return +2.0%" }, { id: "about", d: null, title: "How", text: "Simulated money." }];

test("no AI binding -> 503, browser falls back to search only", async () => {
  const r = await onRequestPost({ request: req({ q: "hi", passages: P }), env: {} });
  assert.equal(r.status, 503);
});
test("answer keeps only citations of passages it was given, and only allowed actions", async () => {
  const AI = { run: async () => ({ response: JSON.stringify({ answer: "Arrow-01 is up 2%.", cite: ["p:arrow-01", "made-up"], actions: [{ type: "open", id: "arrow-01" }, { type: "rm -rf" }] }) }) };
  const r = await onRequestPost({ request: req({ q: "how is Arrow-01?", passages: P }), env: { AI } });
  const j = await r.json();
  assert.equal(r.status, 200);
  assert.deepEqual(j.cite, ["p:arrow-01"]);
  assert.deepEqual(j.actions, [{ type: "open", id: "arrow-01" }]);
});
test("the prompt carries the as-of date and only the given passages", async () => {
  let seen = "";
  const AI = { run: async (_m, x) => { seen = x.messages[1].content; return { response: "{\"answer\":\"ok\",\"cite\":[]}" }; } };
  await onRequestPost({ request: req({ q: "x", asOf: "2026-11-05", passages: P }), env: { AI } });
  assert.match(seen, /as of: 2026-11-05/);
  assert.match(seen, /\[p:arrow-01\]/);
});
test("free allocation used up -> 429 quota", async () => {
  const AI = { run: async () => { throw new Error("daily neuron limit exceeded"); } };
  const r = await onRequestPost({ request: req({ q: "x", passages: P }), env: { AI } });
  assert.equal(r.status, 429);
  assert.equal((await r.json()).error, "quota");
});
test("empty question -> 400", async () => {
  const r = await onRequestPost({ request: req({ q: "  ", passages: P }), env: { AI: { run: async () => ({}) } } });
  assert.equal(r.status, 400);
});
