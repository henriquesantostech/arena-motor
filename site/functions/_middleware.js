// Login gate for the private site (Cloudflare Pages Function; runs before every file, data included).
// Sign-in with GitHub; only the GitHub accounts in ALLOWED_GITHUB_USERS get in. The session is a signed,
// HttpOnly cookie (HMAC-SHA256 with SESSION_KEY), valid 30 days. Nothing is served without it.
// Environment (Pages project secrets): GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, SESSION_KEY, ALLOWED_GITHUB_USERS.
const COOKIE = "arena_session", STATE = "arena_state", DAYS = 30;
const enc = new TextEncoder();

const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
async function hmac(key, text) {
  const k = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64u(await crypto.subtle.sign("HMAC", k, enc.encode(text)));
}
function same(a, b) { // constant-time comparison
  if (a.length !== b.length) return false;
  let d = 0; for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
function cookies(req) {
  const out = {};
  (req.headers.get("Cookie") || "").split(/;\s*/).forEach(c => { const i = c.indexOf("="); if (i > 0) out[c.slice(0, i)] = c.slice(i + 1); });
  return out;
}
const allowed = env => (env.ALLOWED_GITHUB_USERS || "").toLowerCase().split(/[,;\s]+/).filter(Boolean);
const page = (status, title, body) => new Response(
  `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>${title}</title>` +
  `<body style="margin:0;height:100vh;display:grid;place-items:center;background:#05070d;color:#e8edf7;font:15px system-ui,sans-serif;text-align:center">` +
  `<div><div style="font-size:20px;font-weight:700;margin-bottom:8px">Arena of Agents</div><div style="color:#8d97ad">${body}</div></div>`,
  { status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex" } });

async function session(req, env) {
  const v = cookies(req)[COOKIE];
  if (!v) return null;
  const [login, exp, sig] = v.split(".");
  if (!login || !exp || !sig || Date.now() / 1000 > Number(exp)) return null;
  if (!same(sig, await hmac(env.SESSION_KEY, `${login}.${exp}`))) return null;
  return allowed(env).includes(login.toLowerCase()) ? login : null;
}

export async function onRequest(ctx) {
  const { request: req, env } = ctx;
  if (!env.GITHUB_CLIENT_ID || !env.GITHUB_CLIENT_SECRET || !env.SESSION_KEY || env.SESSION_KEY.length < 32 || !allowed(env).length)
    return page(503, "Closed", "Closed: the login is not configured.");   // fail closed
  const url = new URL(req.url);
  const secure = "Path=/; HttpOnly; Secure; SameSite=Lax";

  if (url.pathname === "/auth/logout")
    return new Response(null, { status: 302, headers: { Location: "/", "Set-Cookie": `${COOKIE}=; ${secure}; Max-Age=0` } });

  if (url.pathname === "/auth/callback") {
    const state = url.searchParams.get("state") || "", code = url.searchParams.get("code") || "";
    if (!code || !state || !same(state, cookies(req)[STATE] || "")) return page(400, "Sign-in failed", "Sign-in failed. <a style=\"color:#38c6ff\" href=\"/\">Try again</a>.");
    const tok = await fetch("https://github.com/login/oauth/access_token", {
      method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: env.GITHUB_CLIENT_ID, client_secret: env.GITHUB_CLIENT_SECRET, code }),
    }).then(r => r.json()).catch(() => ({}));
    if (!tok.access_token) return page(400, "Sign-in failed", "Sign-in failed. <a style=\"color:#38c6ff\" href=\"/\">Try again</a>.");
    const user = await fetch("https://api.github.com/user", { headers: { Authorization: `Bearer ${tok.access_token}`, "User-Agent": "arena-site", Accept: "application/vnd.github+json" } })
      .then(r => r.json()).catch(() => ({}));
    const login = String(user.login || "");
    if (!login || !allowed(env).includes(login.toLowerCase())) return page(403, "No access", "This GitHub account has no access to this private site.");
    const exp = Math.floor(Date.now() / 1000) + DAYS * 86400;
    const h = new Headers({ Location: "/" });
    h.append("Set-Cookie", `${COOKIE}=${login}.${exp}.${await hmac(env.SESSION_KEY, `${login}.${exp}`)}; ${secure}; Max-Age=${DAYS * 86400}`);
    h.append("Set-Cookie", `${STATE}=; ${secure}; Max-Age=0`);
    return new Response(null, { status: 302, headers: h });
  }

  if (await session(req, env)) {
    const res = await ctx.next();
    const out = new Response(res.body, res);
    out.headers.set("X-Robots-Tag", "noindex, nofollow");
    if (!out.headers.has("Cache-Control") || /data\.js$|\/$|\.html$/.test(url.pathname)) out.headers.set("Cache-Control", "private, no-cache");
    return out;
  }

  // Not signed in: go to GitHub (state cookie guards against forged callbacks)
  const state = b64u(crypto.getRandomValues(new Uint8Array(24)));
  const gh = new URL("https://github.com/login/oauth/authorize");
  gh.searchParams.set("client_id", env.GITHUB_CLIENT_ID);
  gh.searchParams.set("redirect_uri", `${url.origin}/auth/callback`);
  gh.searchParams.set("scope", "");
  gh.searchParams.set("state", state);
  gh.searchParams.set("allow_signup", "false");
  const h = new Headers({ Location: gh.toString(), "Cache-Control": "no-store" });
  h.append("Set-Cookie", `${STATE}=${state}; ${secure}; Max-Age=600`);
  return new Response(null, { status: 302, headers: h });
}
