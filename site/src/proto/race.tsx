// Prototype A — "The Race". Glance: one answer sentence, the race against the market (the bright pacer),
// the luck zone where random monkeys run, and three stories of the day. Click a runner → Story → Detail.
import "@fontsource-variable/geist";
import "./proto.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { buildModel, loadArena, type Arena, type Model, type Participant } from "../data";
import { capital, euro, STRATEGY } from "./common";
import { CreatureSvg, Story, useClock } from "./Story";
import { Bar, Head, Stories, TimeBar, useDay, useTheme } from "./shell";

function App() {
  const [A, setA] = useState<Arena | null>(null);
  useEffect(() => { loadArena("../../").then(setA).catch(() => setA(null)); }, []);
  if (!A) return <div className="app"><p className="quiet">Loading the race…</p></div>;
  return <Race M={buildModel(A)} />;
}

function Race({ M }: { M: Model }) {
  const [dark, setDark] = useTheme();
  const [open, setOpen] = useState<string | null>(null);
  const { i, setI, playing, setPlaying } = useDay(M, useCallback(() => setOpen(null), []));
  const [tip, setTip] = useState<{ p: Participant; x: number; y: number } | null>(null);
  const t = useClock(!open);
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 500 });
  useEffect(() => { const el = box.current!; const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight })); ro.observe(el); return () => ro.disconnect(); }, []);

  const cap = capital(M.A);
  const order = useMemo(() => M.agents.slice().sort((a, b) => M.gapAt(b, i) - M.gapAt(a, i)), [M, i]);
  const pad = 96, laneH = Math.max(10, Math.min(34, (size.h - 24) / Math.max(1, order.length)));
  const span = Math.max(.02, M.span);
  const X = (g: number) => pad + (size.w - pad - 40) * (0.5 + Math.max(-1, Math.min(1, g / span)) / 2);
  const band = M.luckAt(i);
  // drag the track to move through time
  const drag = useRef<{ x: number; i: number } | null>(null);
  const down = (e: React.PointerEvent) => { if ((e.target as HTMLElement).closest(".runner")) return; drag.current = { x: e.clientX, i }; (e.currentTarget as Element).setPointerCapture(e.pointerId); setPlaying(false); };
  const move = (e: React.PointerEvent) => { const d = drag.current; if (!d) return; const k = Math.round(d.i + (e.clientX - d.x) / Math.max(6, size.w / Math.max(8, M.last + 1))); setI(Math.max(0, Math.min(M.last, k))); };
  const up = () => { drag.current = null; };

  return (
    <div className="app">
      <Bar dark={dark} setDark={setDark} />
      <Head M={M} i={i} />
      <div className="main">
        <section className="race card" aria-label="The race">
          <div className="legend"><span className="luckkey">← Behind the market<b className="sep" /><i />Shaded: could be luck</span><span>Ahead of the market →</span></div>
          <div className="track" ref={box} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={() => setTip(null)}>
            {band && <div className="luck" style={{ left: X(band[0]), width: Math.max(4, X(band[1]) - X(band[0])) }} />}
            <div className="pacer" style={{ left: X(0) - 1 }}><span>the market</span></div>
            {M.monkeys.map((m, k) => <i key={m.id} className="monkey" style={{ left: X(M.gapAt(m, i)), top: 8 + ((k * 37) % 100) / 100 * (size.h - 16) }} />)}
            {order.map((p, k) => <div key={"l" + p.id} className="lane" style={{ top: 14 + k * laneH + laneH / 2 }} />)}
            {order.map((p, k) => {
              const g = M.gapAt(p, i), x = X(g), y = 14 + k * laneH + laneH / 2;
              return (
                <button key={p.id} className={"runner" + (open === p.id ? " hot" : "")} style={{ transform: `translate(${x - 90}px, ${y - laneH / 2 - 2}px)` }}
                  onClick={() => setOpen(p.id)} onPointerEnter={e => setTip({ p, x: e.clientX, y: e.clientY })} onPointerLeave={() => setTip(null)}
                  aria-label={`${p.name}: ${euro(Math.abs(g * cap))} ${g >= 0 ? "ahead of" : "behind"} the market`}>
                  <span className="nm">{p.name}</span>
                  <CreatureSvg p={p} size={laneH + 10} dark={dark} t={t} />
                </button>
              );
            })}
            {tip && (() => { const g = M.gapAt(tip.p, i), r = box.current!.getBoundingClientRect(); return (
              <div className="tip" style={{ left: Math.min(tip.x - r.left + 14, size.w - 290), top: Math.min(tip.y - r.top + 14, size.h - 90) }}>
                <b>{tip.p.name}</b><span>{STRATEGY[tip.p.sp || ""]}</span><br />
                <span className={g >= 0 ? "gain" : "loss"}>{euro(Math.abs(g * cap))} {g >= 0 ? "ahead of" : "behind"} the market</span> · <span>now {euro(M.valueAt(tip.p, i))}</span>
              </div>); })()}
          </div>
          <TimeBar M={M} i={i} setI={setI} playing={playing} setPlaying={setPlaying} />
        </section>
        <Stories M={M} i={i} dark={dark} t={t} onOpen={setOpen} />
        {open && M.byId[open] && <Story M={M} p={M.byId[open]} i={i} dark={dark} onClose={() => setOpen(null)} crumbs={["Today"]} />}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
