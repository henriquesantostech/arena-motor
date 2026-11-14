// Quality tiers: Ultra / High / Lite (Lite = the 2D view). Picked from the device, with no network call
// (no GPU benchmark database), then adjusted at run time by the frame rate (see scene/World.tsx).
export type Tier = "ultra" | "high" | "lite";

export function hasWebGL2(): boolean {
  try { return !!document.createElement("canvas").getContext("webgl2"); } catch { return false; }
}

export function detectTier(): Tier {
  if (!hasWebGL2()) return "lite";
  const nav = navigator as Navigator & { deviceMemory?: number };
  const cores = nav.hardwareConcurrency || 4, mem = nav.deviceMemory || 4;
  const phone = matchMedia("(pointer: coarse)").matches && Math.min(screen.width, screen.height) < 820;
  let gpu = "";
  try {
    const gl = document.createElement("canvas").getContext("webgl2")!;
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    gpu = String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)).toLowerCase();
  } catch { /* ignore */ }
  if (/swiftshader|llvmpipe|software|basic render/.test(gpu)) return "lite";
  if (phone || cores <= 4 || mem <= 4 || /intel\(r\) (hd|uhd) graphics [56]\d\d|mali-[gt]\d{2}\b|adreno \(tm\) [1-5]\d\d/.test(gpu)) return "high";
  return "ultra";
}

const KEY = "arena.tier";
export function savedTier(): Tier | null {
  try { const v = localStorage.getItem(KEY); return v === "ultra" || v === "high" || v === "lite" ? v : null; } catch { return null; }
}
export function saveTier(t: Tier) { try { localStorage.setItem(KEY, t); } catch { /* private mode */ } }
