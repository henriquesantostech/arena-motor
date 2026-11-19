import { chromium } from "playwright-core";
const [url, out, theme] = process.argv.slice(2);
const b = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const p = await b.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: theme || "light" });
const errs = []; p.on("pageerror", e => errs.push(String(e)));
await p.goto(url); await p.waitForTimeout(2500);
await p.screenshot({ path: out }); console.log("errors:", errs.join(" | ") || "none"); await b.close();
