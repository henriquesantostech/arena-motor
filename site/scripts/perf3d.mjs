// 3D arrival time on THIS computer's real GPU (Edge/Chrome, headless but hardware-accelerated).
// Usage: node scripts/perf3d.mjs <url> [runs]   e.g. node scripts/perf3d.mjs http://127.0.0.1:8765/ 3
// Prints, per variant: GPU name, when the 3D chunk ran, first 3D callback and first 3D frame on screen.
import { chromium } from "playwright-core";

const url = process.argv[2] || "http://127.0.0.1:8765/";
const runs = +(process.argv[3] || 3);
const variants = (process.env.VARIANTS ?? ",fx=0,tx=0,fx=0&tx=0").split(",");
const browser = await chromium.launch({ channel: process.env.PERF_CHANNEL || "msedge", headless: true,
  args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu-rasterization"] });
const page0 = await browser.newPage();
await page0.goto(url);
const gpu = await page0.evaluate(() => { const g = document.createElement("canvas").getContext("webgl2"); const e = g?.getExtension("WEBGL_debug_renderer_info"); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : "no webgl2"; });
console.log("GPU:", gpu);
await page0.evaluate(() => localStorage.setItem("arena.tier", "ultra"));
await page0.close();
for (const v of variants) {
  const rows = [];
  for (let k = 0; k < runs; k++) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    if (process.env.THROTTLE) {   // broadband-like: 40 ms latency, 25 Mbit/s down
      const cdp = await page.context().newCDPSession(page);
      await cdp.send("Network.enable");
      await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 40, downloadThroughput: 25e6 / 8, uploadThroughput: 5e6 / 8 });
      await cdp.send("Network.setCacheDisabled", { cacheDisabled: !!process.env.COLD });
    }
    await page.goto(`${url}?run=${k}${v ? "&" + v : ""}`);
    await page.waitForFunction(() => window.ARENA_PERF && window.ARENA_PERF.drawn > 0, null, { timeout: 30000 }).catch(() => {});
    rows.push(await page.evaluate(() => window.ARENA_PERF));
    await page.close();
  }
  const med = key => { const a = rows.map(r => r[key]).filter(x => x > 0).sort((a, b) => a - b); return a.length ? a[Math.floor(a.length / 2)] : -1; };
  console.log(`${(v || "default").padEnd(10)} ui ${med("ui")} ms · 3D chunk ${med("chunk")} ms · first callback ${med("world")} ms · 3D on screen ${med("drawn")} ms`);
}
await browser.close();
