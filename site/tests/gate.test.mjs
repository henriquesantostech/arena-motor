// Tests for the login gate. Run: node --test site/tests/
import test from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { onRequest } from "../functions/_middleware.js";

const env = { GITHUB_CLIENT_ID: "id", GITHUB_CLIENT_SECRET: "secret", SESSION_KEY: "k".repeat(40), ALLOWED_GITHUB_USERS: "Alice, bob" };
const sign = (login, exp, key = env.SESSION_KEY) => `${login}.${exp}.` + createHmac("sha256", key).update(`${login}.${exp}`).digest("base64url");
const run = async (path, { cookie, e = env } = {}) => {
  let served = false;
  const req = new Request("https://arena.example" + path, { headers: cookie ? { Cookie: cookie } : {} });
  const res = await onRequest({ request: req, env: e, next: async () => { served = true; return new Response("SECRET DATA", { headers: { "Content-Type": "text/plain" } }); } });
  return { res, served };
};
const later = () => Math.floor(Date.now() / 1000) + 3600;

test("not configured -> closed", async () => {
  const { res, served } = await run("/", { e: {} });
  assert.equal(res.status, 503); assert.equal(served, false);
});
test("no session -> sent to GitHub, nothing served (page and data)", async () => {
  for (const p of ["/", "/data.js", "/app.js?v=1"]) {
    const { res, served } = await run(p);
    assert.equal(res.status, 302); assert.equal(served, false);
    assert.match(res.headers.get("Location"), /^https:\/\/github\.com\/login\/oauth\/authorize\?/);
  }
});
test("valid session for an allowed user -> served", async () => {
  const { res, served } = await run("/data.js", { cookie: "arena_session=" + sign("alice", later()) });
  assert.equal(served, true); assert.equal(res.status, 200);
  assert.equal(await res.text(), "SECRET DATA");
});
test("forged, expired or not-allowed sessions -> refused", async () => {
  for (const c of [sign("alice", later(), "x".repeat(40)), sign("alice", 1000), sign("mallory", later()), "alice." + later() + ".AAAA", "junk"]) {
    const { served } = await run("/", { cookie: "arena_session=" + c });
    assert.equal(served, false, c);
  }
});
test("callback without matching state -> refused", async () => {
  const { res, served } = await run("/auth/callback?code=x&state=abc", { cookie: "arena_state=other" });
  assert.equal(res.status, 400); assert.equal(served, false);
});
