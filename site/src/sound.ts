// Optional UI sound, OFF by default: soft ticks, a whoosh between lenses and a chime for answers.
// Synthesised with Web Audio (no sound files, nothing downloaded). Respects the user's choice, saved locally.
let ctx: AudioContext | null = null;
let on = (() => { try { return localStorage.getItem("arena.sound") === "1"; } catch { return false; } })();

export const soundOn = () => on;
export function setSound(v: boolean) { on = v; try { localStorage.setItem("arena.sound", v ? "1" : "0"); } catch { /* private mode */ } if (v) tick(); }

function ac() { if (!ctx) ctx = new AudioContext(); if (ctx.state === "suspended") ctx.resume(); return ctx; }
function tone(freq: number, dur: number, type: OscillatorType = "sine", gain = .05, slide = 0) {
  if (!on) return;
  try {
    const a = ac(), o = a.createOscillator(), g = a.createGain(), t = a.currentTime;
    o.type = type; o.frequency.setValueAtTime(freq, t); if (slide) o.frequency.exponentialRampToValueAtTime(freq * slide, t + dur);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + .01); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(g).connect(a.destination); o.start(t); o.stop(t + dur + .02);
  } catch { /* audio unavailable */ }
}
export const tick = () => tone(1800, .05, "triangle", .025);
export const whoosh = () => tone(220, .28, "sine", .04, 2.2);
export const chime = () => { tone(880, .35, "sine", .035); setTimeout(() => tone(1320, .4, "sine", .025), 90); };
export const low = () => tone(110, .5, "sine", .05);
