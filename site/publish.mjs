// Publishes the private site to Cloudflare Pages, behind Cloudflare Access (login).
// Safety first: it never uploads unless the login gate covers the address, and after uploading it
// checks from outside that the page and the data ask for a login. Any doubt -> stop with an error.
//
// Usage (GitHub Actions, see .github/workflows/site.yml):
//   CLOUDFLARE_API_TOKEN=...  ARENA_ALLOWED_EMAILS="a@x.com,b@y.com"  node site/publish.mjs <folder>
// The token needs: Account · Cloudflare Pages · Edit, Account · Access: Apps and Policies · Edit,
// Account · Account Settings · Read. Logs never print e-mails or tokens (the engine repo is public).
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";

const PROJECT = process.env.ARENA_PAGES_PROJECT || "arena-agents";
const APP_NAME = "Arena of Agents";
const POLICY_NAME = "Arena owners";
const WRANGLER = "wrangler@4.154.0";
const API = "https://api.cloudflare.com/client/v4";
const token = process.env.CLOUDFLARE_API_TOKEN;
const emails = (process.env.ARENA_ALLOWED_EMAILS || "").split(/[,;\s]+/).filter(e => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e));
const dir = process.argv[2];

const fail = msg => { console.error("STOP: " + msg); process.exit(1); };
if (!token) { console.log("not configured yet (no CLOUDFLARE_API_TOKEN): nothing published"); process.exit(0); }
if (!emails.length) fail("missing ARENA_ALLOWED_EMAILS (who may log in)");
if (!dir || !existsSync(dir + "/index.html") || !existsSync(dir + "/data.js")) fail("site folder not found");

async function cf(method, path, body) {
  const r = await fetch(API + path, {
    method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (r.status === 404 && method === "GET") return null;
  if (!r.ok || j.success === false) fail(`${method} ${path.replace(/[0-9a-f]{32}/g, "…")} -> ${r.status} ${(j.errors || []).map(e => e.code + " " + e.message).join("; ")}`);
  return j.result;
}

const accounts = await cf("GET", "/accounts");
if (!accounts || accounts.length !== 1) fail(`expected exactly one Cloudflare account, found ${accounts ? accounts.length : 0}`);
const acc = accounts[0].id;

// 1. Pages project (created empty the first time: nothing is public until the gate exists)
let project = await cf("GET", `/accounts/${acc}/pages/projects/${PROJECT}`);
if (!project) project = await cf("POST", `/accounts/${acc}/pages/projects`, { name: PROJECT, production_branch: "main" });
const host = project.subdomain;   // e.g. arena-agents.pages.dev (or with a suffix if the name was taken)
if (!host || !host.endsWith(".pages.dev")) fail("unexpected project address");

// 2. Login gate: one Access application covering the address and every deployment preview (*.address)
const want = [host, "*." + host];
const policies = await cf("GET", `/accounts/${acc}/access/policies`);
let policy = (policies || []).find(p => p.name === POLICY_NAME);
const policyBody = { name: POLICY_NAME, decision: "allow", include: emails.map(email => ({ email: { email } })), session_duration: "720h" };
policy = policy ? await cf("PUT", `/accounts/${acc}/access/policies/${policy.id}`, policyBody)
  : await cf("POST", `/accounts/${acc}/access/policies`, policyBody);
const apps = await cf("GET", `/accounts/${acc}/access/apps`);
let app = (apps || []).find(a => a.name === APP_NAME);
const appBody = {
  name: APP_NAME, type: "self_hosted", domain: host, session_duration: "720h",
  destinations: want.map(uri => ({ type: "public", uri })),
  policies: [{ id: policy.id, precedence: 1 }],
  app_launcher_visible: false, auto_redirect_to_identity: false,
};
app = app ? await cf("PUT", `/accounts/${acc}/access/apps/${app.id}`, appBody) : await cf("POST", `/accounts/${acc}/access/apps`, appBody);
const covered = new Set([app.domain, ...(app.self_hosted_domains || []), ...(app.destinations || []).map(d => d.uri)]);
if (!want.every(u => covered.has(u))) fail("the login gate does not cover the whole address");
console.log(`login gate ok (${emails.length} people allowed)`);

async function gated(label) {
  for (const path of ["/", "/data.js"]) {
    let ok = false;
    for (let i = 0; i < 9 && !ok; i++) {
      const r = await fetch(`https://${host}${path}`, { redirect: "manual" }).catch(() => null);
      const loc = (r && r.headers.get("location")) || "";
      ok = !!r && ((r.status === 302 || r.status === 303) && /cloudflareaccess\.com/.test(loc) || r.status === 401 || r.status === 403);
      if (!ok) await new Promise(res => setTimeout(res, 10000));
    }
    if (!ok) fail(`${label}: ${path} answers without a login. Check Cloudflare Access now.`);
  }
}

// 3. Before uploading: from outside, the address must already ask for a login.
await gated("before upload");

// 4. Upload
execFileSync("npx", ["--yes", WRANGLER, "pages", "deploy", dir, "--project-name", PROJECT, "--branch", "main", "--commit-dirty=true"], {
  stdio: ["ignore", "ignore", "inherit"], env: { ...process.env, CLOUDFLARE_ACCOUNT_ID: acc }, shell: process.platform === "win32",
});

// 5. After uploading: same check (the address itself is never printed: these logs are public).
await gated("after upload");
console.log("published; login required");
