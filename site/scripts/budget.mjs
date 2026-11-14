// Performance budget for every build (Experience v2, section 6). Fails the build when broken.
// - initial JavaScript (what index.html loads before the first frame) < 200 KB compressed
// - the 3D world is a separate chunk, loaded after the first frame (reported, budget 450 KB)
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const dist = new URL("../dist/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
const html = readFileSync(join(dist, "index.html"), "utf8");
const gz = f => gzipSync(readFileSync(join(dist, f)), { level: 9 }).length;
const kb = b => (b / 1024).toFixed(1) + " KB";

const initial = [...html.matchAll(/<(?:script[^>]+src|link[^>]+rel="(?:stylesheet|modulepreload)"[^>]+href)="\.?\/?([^"]+\.(?:js|css))"/g)].map(m => m[1]);
const initialJs = initial.filter(f => f.endsWith(".js")).reduce((s, f) => s + gz(f), 0);
const initialCss = initial.filter(f => f.endsWith(".css")).reduce((s, f) => s + gz(f), 0);
const assets = readdirSync(join(dist, "assets"));
const world = assets.filter(f => f.endsWith(".js") && !initial.includes("assets/" + f)).reduce((s, f) => s + gz("assets/" + f), 0);
const fonts = assets.filter(f => f.endsWith(".woff2")).reduce((s, f) => s + statSync(join(dist, "assets", f)).size, 0);

const rows = [["initial JS", initialJs, 200 * 1024], ["initial CSS", initialCss, 40 * 1024], ["3D world (lazy)", world, 450 * 1024]];
let ok = true;
for (const [name, size, max] of rows) {
  const pass = size <= max; ok &&= pass;
  console.log(`${pass ? "ok  " : "FAIL"} ${name.padEnd(18)} ${kb(size).padStart(9)}  (budget ${kb(max)})`);
}
console.log(`     fonts (woff2, all subsets, loaded on use) ${kb(fonts)}`);
if (!initial.some(f => f.endsWith(".js"))) { console.log("FAIL no initial script found"); ok = false; }
if (!ok) process.exit(1);
