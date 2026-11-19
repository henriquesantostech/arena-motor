// What both prototypes share around the picture: theme, the top bar with the three doors, the answer
// sentence and the stories of the day. Only the picture in the middle differs (2D race vs 3D world).
import { useEffect, useState } from "react";
import { ROOT, type Model, type Participant } from "../data";
import { dayName, euro, headline, sentence } from "./common";
import { CreatureSvg } from "./Story";

export function useTheme() {
  const [dark, setDark] = useState(() => { try { const v = localStorage.getItem("arena.v3.theme"); if (v) return v === "dark"; } catch { /* */ } return matchMedia("(prefers-color-scheme: dark)").matches; });
  useEffect(() => { document.documentElement.dataset.theme = dark ? "dark" : "light"; try { localStorage.setItem("arena.v3.theme", dark ? "dark" : "light"); } catch { /* */ } }, [dark]);
  return [dark, setDark] as const;
}

export function Bar({ dark, setDark }: { dark: boolean; setDark: (d: boolean) => void }) {
  return (
    <header className="bar">
      <div className="brand"><svg width="22" height="22" viewBox="-11 -11 22 22"><circle r="9" fill="var(--market)" opacity=".9" /></svg>Agent Arena <span className="quiet">· trial · pretend money</span></div>
      <nav className="doors" aria-label="Main">
        <button className="on">Today</button><a href={ROOT + "classic/"}>Explore</a><a href={ROOT + "classic/"} title="Ask is being rebuilt; opens the current one">Ask</a>
      </nav>
      <div className="settings"><a className="full" href={ROOT + "classic/"}>Full detail</a><button onClick={() => setDark(!dark)}>{dark ? "Light" : "Dark"}</button></div>
    </header>
  );
}

export function Head({ M, i }: { M: Model; i: number }) {
  const H = headline(M, i);
  return <section className="head"><h1>{H.big}</h1><p>{H.small}</p></section>;
}

export function storiesOf(M: Model, i: number) {
  const day = M.A.meta.dates[i];
  const daily = i > 0 ? M.agents.map(p => ({ p, eur: (M.valueAt(p, i) - M.valueAt(p, i - 1)) })).sort((a, b) => Math.abs(b.eur) - Math.abs(a.eur)) : [];
  const trades = M.agents.flatMap(p => p.log.filter(m => m.d === day && (m.k === "buy" || m.k === "sell")).map(m => ({ p, m }))).sort((a, b) => (b.m.eur || 0) - (a.m.eur || 0));
  const lastDeath = (M.A.dead || []).slice().sort((a, b) => (b.dead?.died || "").localeCompare(a.dead?.died || ""))[0];
  const best = M.agents.slice().sort((a, b) => M.gapAt(b, i) - M.gapAt(a, i))[0];
  return [
    daily[0] && { p: daily[0].p, k: "Biggest move today", s: `${daily[0].p.name} ${daily[0].eur >= 0 ? "gained" : "lost"} ${euro(Math.abs(daily[0].eur))} on ${dayName(day)}.` },
    trades[0] && { p: trades[0].p, k: "A decision", s: `${trades[0].p.name}: ${sentence(M.A, trades[0].m)}` },
    lastDeath ? { p: lastDeath, k: "The graveyard", s: `${lastDeath.name} died on ${dayName(lastDeath.dead!.died)}, ranked ${lastDeath.dead!.rank} of ${lastDeath.dead!.of}.` }
      : best && { p: best, k: "Is it skill or luck?", s: best.pctAll != null ? `The leader, ${best.name}, beats ${Math.round(best.pctAll * 100)}% of 1,000 random monkeys. Merit needs 95% for a year.` : `Too early to tell skill from luck: merit needs a year.` },
  ].filter(Boolean) as { p: Participant; k: string; s: string }[];
}

export function Stories({ M, i, dark, t, onOpen }: { M: Model; i: number; dark: boolean; t: number; onOpen: (id: string) => void }) {
  return (
    <section className="stories" aria-label="Today's stories">
      {storiesOf(M, i).map((s, k) => (
        <button key={k} className="storycard card" onClick={() => onOpen(s.p.id)}>
          <CreatureSvg p={s.p} size={56} dark={dark} t={t} />
          <span><span className="k">{s.k}</span><br /><span className="s">{s.s}</span></span>
        </button>
      ))}
      <div className="quiet" style={{ fontSize: 13, padding: "0 4px" }}>Pretend money only, never advice. Tap any creature to see why it is ahead or behind.</div>
    </section>
  );
}

export function TimeBar({ M, i, setI, playing, setPlaying }: { M: Model; i: number; setI: (k: number) => void; playing: boolean; setPlaying: (b: boolean) => void }) {
  return (
    <div className="time">
      <button className="play" onClick={() => { if (i >= M.last) setI(0); setPlaying(!playing); }} aria-label={playing ? "Pause" : "Play the season"}>{playing ? "❚❚" : "▶"}</button>
      <input type="range" min={0} max={M.last} value={i} onChange={e => { setPlaying(false); setI(+e.target.value); }} aria-label="Day" />
      <span className="d num">{dayName(M.A.meta.dates[i])}</span>
    </div>
  );
}

/** Day index + play loop + arrow keys, shared. */
export function useDay(M: Model, onEscape: () => void) {
  const [i, setI] = useState(M.last);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setI(k => { if (k >= M.last) { setPlaying(false); return k; } return k + 1; }), 450);
    return () => clearInterval(id);
  }, [playing, M.last]);
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === "Escape") onEscape(); if (e.key === "ArrowLeft") setI(x => Math.max(0, x - 1)); if (e.key === "ArrowRight") setI(x => Math.min(M.last, x + 1)); }; addEventListener("keydown", k); return () => removeEventListener("keydown", k); }, [M.last, onEscape]);
  return { i, setI, playing, setPlaying };
}
