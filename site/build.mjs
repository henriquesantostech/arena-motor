// Builds site/dist from site/src: two minified bundles (app.js = page, arena3d.js = Three.js scene,
// loaded after the first paint), with content hashes in the URLs so browsers can cache them forever.
// Run: npm run build   (Python's `arena site` only copies dist/ and writes data.js next to it)
import { build } from "esbuild";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, rmSync, writeFileSync, copyFileSync } from "node:fs";

const src = new URL("./src/", import.meta.url), out = new URL("./dist/", import.meta.url);
const hash = b => createHash("sha256").update(b).digest("hex").slice(0, 10);
const common = { bundle: true, minify: true, format: "iife", target: ["es2020"], legalComments: "none", write: false, charset: "utf8" };

rmSync(out, { recursive: true, force: true });
mkdirSync(out);
const three = (await build({ ...common, entryPoints: [new URL("arena3d.js", src).pathname.replace(/^\/(\w:)/, "$1")] })).outputFiles[0].contents;
const h3 = hash(three);
const app = (await build({ ...common, entryPoints: [new URL("app.js", src).pathname.replace(/^\/(\w:)/, "$1")], define: { ARENA_3D_URL: JSON.stringify("arena3d.js?v=" + h3) } })).outputFiles[0].contents;
const cssIn = readFileSync(new URL("style.css", src));
const css = (await build({ ...common, bundle: false, format: undefined, loader: { ".css": "css" }, stdin: { contents: cssIn.toString(), loader: "css" } })).outputFiles[0].contents;
writeFileSync(new URL("arena3d.js", out), three);
writeFileSync(new URL("app.js", out), app);
writeFileSync(new URL("style.css", out), css);
const html = readFileSync(new URL("index.html", src), "utf8").replace("__CSS__", hash(css)).replace("__APP__", hash(app)).replace("__3D__", h3);
writeFileSync(new URL("index.html", out), html);
for (const f of ["favicon.svg", "_headers"]) copyFileSync(new URL(f, src), new URL(f, out));
const kb = b => (b.length / 1024).toFixed(1) + " KB";
console.log(`app.js ${kb(app)} · arena3d.js ${kb(three)} · style.css ${kb(css)}`);
