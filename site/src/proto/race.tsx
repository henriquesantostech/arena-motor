// Prototype A — "The Race". Glance: one answer sentence, the race against the market (the bright pacer),
// the luck zone where random monkeys run, and three stories of the day. Click a runner → Story → Detail.
import "@fontsource-variable/geist";
import "./proto.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { buildModel, loadArena, type Arena, type Model, type Participant } from "../data";
import { capital, company, dayName, euro, headline, sentence, STRATEGY } from "./common";
import { CreatureSvg, Story, useClock } from "./Story";

function useTheme() {
  const [dark, setDark] = useState(() => { try { const v = localStorage.getItem("arena.v3.theme"); if (v) return v === "dark"; } catch { /* */ } return matchMedia("(prefers-color-scheme: dark)").matches; });
  useEffect(() => { document.documentElement.dataset.theme = dark ? "dark" : "light"; try { localStorage.setItem("arena.v3.theme", dark ? "dark" : "light"); } catch { /* */ } }, [dark]);
  return [dark, setDark] as const;
}

function App() {
  const [A, setA] = useState<Arena | null>(null);
  useEffect(() => { loadArena("../../").then(setA).catch(() => setA(null)); }, []);
  if (!A) return <div className="app"><p className="quiet">Loading the race…</p></div>;
  return <Race M={buildModel(A)} />;
}

function Race({ M }: { M: Model }) {
  const [dark, setDark] = useTheme();
  const [i, setI] = useState(M.last);
  const [playing, setPlaying] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [tip, setTip] = useState<{ p: Participant; x: number; y: number } | null>(null);
  const t = useClock(!open);
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 500 });
  useEffect(() => { const el = box.current!; const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight })); ro.observe(el); return () => ro.disconnect(); }, []);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setI(k => { if (k >= M.last) { setPlaying(false); return k; } return k + 1; }), 450);
    return () => clearInterval(id);
  }, [playing, M.last]);
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); if (e.key === "ArrowLeft") setI(x => Math.max(0, x - 1)); if (e.key === "ArrowRight") setI(x => Math.min(M.last, x + 1)); }; addEventListener("keydown", k); return () => removeEventListener("keydown", k); }, [M.last]);

  const H = headline(M, i), cap = capital(M.A);
  const order = useMemo(() => M.agents.slice().sort((a, b) => M.gapAt(b, i) - M.gapAt(a, i)), [M, i]);
  const pad = 96, laneH = Math.max(18, Math.min(34, (size.h - 30) / Math.max(1, order.length)));
  const span = Math.max(.02, M.span);
  const X = (g: number) => pad + (size.w - pad - 40) * (0.5 + Math.max(-1, Math.min(1, g / span)) / 2);
  const band = M.luckAt(i);
  // drag the track to move through time
  const drag = useRef<{ x: number; i: number } | null>(null);
  const down = (e: React.PointerEvent) => { if ((e.target as HTMLElement).closest(".runner")) return; drag.current = { x: e.clientX, i }; (e.currentTarget as Element).setPointerCapture(e.pointerId); setPlaying(false); };
  const move = (e: React.PointerEvent) => { const d = drag.current; if (!d) return; const k = Math.round(d.i + (e.clientX - d.x) / Math.max(6, size.w / Math.max(8, M.last + 1))); setI(Math.max(0, Math.min(M.last, k))); };
  const up = () => { drag.current = null; };

  // three stories of the day
  const day = M.A.meta.dates[i];
  const daily = i > 0 ? M.agents.map(p => ({ p, eur: (M.valueAt(p, i) - M.valueAt(p, i - 1)) })).sort((a, b) => Math.abs(b.eur) - Math.abs(a.eur)) : [];
  const trades = M.agents.flatMap(p => p.log.filter(m => m.d === day && (m.k === "buy" || m.k === "sell")).map(m => ({ p, m }))).sort((a, b) => (b.m.eur || 0) - (a.m.eur || 0));
  const lastDeath = (M.A.dead || []).slice().sort((a, b) => (b.dead?.died || "").localeCompare(a.dead?.died || ""))[0];
  const best = order[0];
  const stories = [
    daily[0] && { p: daily[0].p, k: "Biggest move today", s: `${daily[0].p.name} ${daily[0].eur >= 0 ? "gained" : "lost"} ${euro(Math.abs(daily[0].eur))} on ${dayName(day)}.` },
    trades[0] && { p: trades[0].p, k: "A decision", s: `${trades[0].p.name}: ${sentence(M.A, trades[0].m)}` },
    lastDeath ? { p: lastDeath, k: "The graveyard", s: `${lastDeath.name} died on ${dayName(lastDeath.dead!.died)}, ranked ${lastDeath.dead!.rank} of ${lastDeath.dead!.of}.` }
      : best && { p: best, k: "Is it skill or luck?", s: best.pctAll != null ? `The leader, ${best.name}, beats ${Math.round(best.pctAll * 100)}% of 1,000 random monkeys. Merit needs 95% for a year.` : `Too early to tell skill from luck: merit needs a year.` },
  ].filter(Boolean) as { p: Participant; k: string; s: string }[];

  return (
    <div className="app">
      <header className="bar">
        <div className="brand"><svg width="22" height="22" viewBox="-11 -11 22 22"><circle r="9" fill="var(--market)" opacity=".9" /></svg>Agent Arena <span className="quiet">· trial · pretend money</span></div>
        <nav className="doors" aria-label="Main">
          <button className="on">Today</button><a href="../../">Explore</a><a href="../../" title="Ask is being rebuilt; opens the current one">Ask</a>
        </nav>
        <div className="settings"><button onClick={() => setDark(!dark)}>{dark ? "Light" : "Dark"}</button></div>
      </header>
      <section className="head"><h1>{H.big}</h1><p>{H.small}</p></section>
      <div className="main">
        <section className="race card" aria-label="The race">
          <div className="legend"><span>← Behind the market</span><span>Ahead of the market →</span></div>
          <div className="track" ref={box} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={() => setTip(null)}>
            {band && <div className="luck" style={{ left: X(band[0]), width: Math.max(4, X(band[1]) - X(band[0])) }}><span>could be luck</span></div>}
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
          <div className="time">
            <button className="play" onClick={() => { if (i >= M.last) setI(0); setPlaying(!playing); }} aria-label={playing ? "Pause" : "Play the season"}>{playing ? "❚❚" : "▶"}</button>
            <input type="range" min={0} max={M.last} value={i} onChange={e => { setPlaying(false); setI(+e.target.value); }} aria-label="Day" />
            <span className="d num">{dayName(day)}</span>
          </div>
        </section>
        <section className="stories" aria-label="Today's stories">
          {stories.map((s, k) => (
            <button key={k} className="storycard card" onClick={() => setOpen(s.p.id)}>
              <CreatureSvg p={s.p} size={56} dark={dark} t={t} />
              <span><span className="k">{s.k}</span><br /><span className="s">{s.s}</span></span>
            </button>
          ))}
          <div className="quiet" style={{ fontSize: 13, padding: "0 4px" }}>Pretend money only, never advice. Tap any creature to see why it is ahead or behind. {company(M.A, "^SP500TR") && ""}</div>
        </section>
        {open && M.byId[open] && <Story M={M} p={M.byId[open]} i={i} dark={dark} onClose={() => setOpen(null)} crumbs={["Today"]} />}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
