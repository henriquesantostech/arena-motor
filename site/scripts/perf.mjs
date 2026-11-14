// Speed check in a real browser (headless Chromium), on the built site with synthetic data.
// Budgets (Experience v2, section 6): first useful frame < 1.0 s, interactive < 1.5 s.
// Usage: npm run build && node scripts/fixture.mjs .perf && node scripts/perf.mjs
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { chromium } from "playwright-core";

const dist = new URL("../dist/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
const fixture = new URL("../.perf/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");   // synthetic data, never shipped
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
const server = createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^[\\/]+/, "") || "index.html";
  try { const b = await readFile(join(path.startsWith("data") ? fixture : dist, path)); res.writeHead(200, { "Content-Type": types[extname(path)] || "application/octet-stream" }); res.end(b); }
  catch { res.writeHead(404); res.end(); }
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch({ channel: process.env.PERF_CHANNEL || undefined, args: ["--enable-unsafe-swiftshader"] });
const runs = [];
for (const [name, viewport] of [["desktop", { width: 1440, height: 900 }], ["phone", { width: 390, height: 844 }]]) {
  const page = await browser.newPage({ viewport });
  const errors = []; page.on("pageerror", e => errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "load" });
  await page.waitForFunction(() => window.ARENA_PERF && window.ARENA_PERF.ui > 0 && (window.ARENA_PERF.flat > 0 || window.ARENA_PERF.world > 0), null, { timeout: 15000 });
  const r = await page.evaluate(() => window.ARENA_PERF);
  const firstUseful = Math.min(...[r.flat, r.world].filter(x => x > 0));
  runs.push({ name, firstUseful, interactive: r.ui, errors });
  await page.close();
}
await browser.close(); server.close();
let ok = true;
for (const r of runs) {
  const pass = r.firstUseful < 1000 && r.interactive < 1500 && !r.errors.length; ok &&= pass;
  console.log(`${pass ? "ok  " : "FAIL"} ${r.name.padEnd(8)} first useful frame ${r.firstUseful} ms (< 1000) · interactive ${r.interactive} ms (< 1500)${r.errors.length ? " · errors: " + r.errors.join("; ") : ""}`);
}
if (!ok) process.exit(1);
