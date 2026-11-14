// Publishes the private site to Cloudflare Pages behind a GitHub sign-in (site/functions/_middleware.js).
// Safety first: the gate ships in the same upload as the files, the gate itself fails closed, and after
// uploading we check from outside that the page and the data ask for a login. If not, the site is
// replaced at once by a "closed" page and the run stops with an error.
//
// Usage (GitHub Actions, see .github/workflows/site.yml):  node site/publish.mjs <site folder>
// Env: CLOUDFLARE_API_TOKEN (Account · Cloudflare Pages · Edit + Account Settings · Read),
//      GH_OAUTH_CLIENT_ID, GH_OAUTH_CLIENT_SECRET (GitHub OAuth app), ARENA_ALLOWED_USERS (GitHub accounts),
//      ARENA_SESSION_KEY (optional).
// Logs are public (engine repo): never print addresses, accounts, keys or data.
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createHash } from "node:crypto";

const PROJECT = process.env.ARENA_PAGES_PROJECT || "arena-agents";
const WRANGLER = "wrangler@4.154.0";
const API = "https://api.cloudflare.com/client/v4";
const E = process.env;
const dir = process.argv[2] && resolve(process.argv[2]);
const here = new URL(".", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");

const fail = msg => { console.error("STOP: " + msg); process.exit(1); };
if (!E.CLOUDFLARE_API_TOKEN) { console.log("not configured yet (no Cloudflare key): nothing published"); process.exit(0); }

async function cf(method, path, body) {
  const r = await fetch(API + path, {
    method, headers: { Authorization: `Bearer ${E.CLOUDFLARE_API_TOKEN}`, "Content-Type": "application/json" },
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

// 1. Project (empty the first time: nothing is online until the first upload)
let project = await cf("GET", `/accounts/${acc}/pages/projects/${PROJECT}`);
if (!project) project = await cf("POST", `/accounts/${acc}/pages/projects`, { name: PROJECT, production_branch: "main" });
const host = project.subdomain;
if (!host || !host.endsWith(".pages.dev")) fail("unexpected project address");
console.log("project ok");

const users = (E.ARENA_ALLOWED_USERS || "").split(/[,;\s]+/).filter(u => /^[A-Za-z0-9-]{1,39}$/.test(u));
// Session signing key: its own secret if given, else derived from the OAuth secret (rotating that one signs everyone out).
const sessionKey = (E.ARENA_SESSION_KEY || "").length >= 32 ? E.ARENA_SESSION_KEY
  : E.GH_OAUTH_CLIENT_SECRET ? createHash("sha256").update("arena-session|" + E.GH_OAUTH_CLIENT_SECRET).digest("base64url") : "";
if (!E.GH_OAUTH_CLIENT_ID || !E.GH_OAUTH_CLIENT_SECRET || !users.length || sessionKey.length < 32) {
  console.log("sign-in not configured yet: project ready, nothing uploaded");
  process.exit(0);
}

if (!dir || !existsSync(join(dir, "index.html")) || !existsSync(join(dir, "data.js"))) fail("site folder not found (the nightly run builds it)");

// 2. Gate settings, as encrypted project secrets (production and previews)
const vars = {
  GITHUB_CLIENT_ID: { type: "secret_text", value: E.GH_OAUTH_CLIENT_ID },
  GITHUB_CLIENT_SECRET: { type: "secret_text", value: E.GH_OAUTH_CLIENT_SECRET },
  SESSION_KEY: { type: "secret_text", value: sessionKey },
  ALLOWED_GITHUB_USERS: { type: "secret_text", value: users.join(",") },
};
await cf("PATCH", `/accounts/${acc}/pages/projects/${PROJECT}`, { deployment_configs: { production: { env_vars: vars }, preview: { env_vars: vars } } });
console.log(`sign-in ok (${users.length} account(s) allowed)`);

// 3. Upload site + gate together
function upload(folder) {
  const stage = mkdtempSync(join(tmpdir(), "arena-"));
  cpSync(folder, join(stage, "public"), { recursive: true });
  mkdirSync(join(stage, "functions"));
  cpSync(join(here, "functions", "_middleware.js"), join(stage, "functions", "_middleware.js"));
  execFileSync("npx", ["--yes", WRANGLER, "pages", "deploy", "public", "--project-name", PROJECT, "--branch", "main", "--commit-dirty=true"], {
    cwd: stage, stdio: ["ignore", "ignore", "inherit"], env: { ...E, CLOUDFLARE_ACCOUNT_ID: acc }, shell: process.platform === "win32",
  });
}
upload(dir);

// 4. Check from outside (the address and the deployment's own address): page and data must ask for a login.
async function gated(base) {
  for (const path of ["/", "/data.js", "/app.js"]) {
    let ok = false;
    for (let i = 0; i < 6 && !ok; i++) {
      const r = await fetch(base + path, { redirect: "manual" }).catch(() => null);
      ok = !!r && r.status === 302 && /^https:\/\/github\.com\/login\/oauth\/authorize/.test(r.headers.get("location") || "");
      if (!ok) await new Promise(res => setTimeout(res, 10000));
    }
    if (!ok) return false;
  }
  return true;
}
const latest = ((await cf("GET", `/accounts/${acc}/pages/projects/${PROJECT}/deployments?env=production`)) || [])[0];
if (!(await gated(`https://${host}`)) || (latest && latest.url && !(await gated(latest.url)))) {
  const closed = mkdtempSync(join(tmpdir(), "arena-closed-"));
  writeFileSync(join(closed, "index.html"), "<!doctype html><meta name=robots content=noindex><title>Closed</title><p>Closed.</p>");
  writeFileSync(join(closed, "data.js"), "");
  upload(closed);
  fail("the site answered without a login: replaced by a closed page. Check the sign-in.");
}
console.log("published; checked from outside: login required");
