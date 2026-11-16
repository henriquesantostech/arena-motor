import { useEffect, useMemo, useRef, useState } from "react";
import { COLOR, colorOf, day, dayY, label, nf, pct, SPECIES_COLOR, tone, type Model, type Participant } from "./data";
import type { Tier } from "./quality";
import { setSound, soundOn, tick } from "./sound";

export type TipState = { id: string; x: number; y: number } | null;
export type Lens = "today" | "arena" | "evolution" | "journal" | "world" | "network" | "lab" | "people";

export function Shape({ p }: { p: Participant }) {
  const c = colorOf(p);
  return p.type === "agent" ? <span className="gem" style={{ background: c }} />
    : p.type === "equal" ? <span className="dot" style={{ border: "2px solid #fff", background: "none" }} />
      : <span className="dot" style={{ background: c }} />;
}

export function Top({ M, i, tier, setTier, gl, lens, setLens, onHelp, onPalette, onAsk, asking }: {
  M: Model; i: number; tier: Tier; setTier: (t: Tier) => void; gl: boolean; lens: Lens; setLens: (l: Lens) => void; onHelp: () => void; onPalette: () => void; onAsk: () => void; asking: boolean;
}) {
  const live = M.A.meta.mode === "live", past = i !== M.last;
  return (
    <header className="top">
      <div className="brand">
        <span className="mark" aria-hidden="true" />
        <b>ARENA</b>
        <span className={"chip where" + (past ? " past" : "")} title={M.A.meta.updated ? "Data as of the market close of this day" : ""}>
          <span className="live" />{past ? "REPLAY" : live ? "LIVE" : "TRIAL"} · <span className="num">DAY {i}</span> · {M.A.meta.dates[i] ? dayY(M.A.meta.dates[i]) : "opens after the first night"}
        </span>
      </div>
      <nav className="dock" aria-label="Lenses">
        {(["today", "arena", "evolution", "journal", "world", "network", "lab", "people"] as Lens[]).map(l => <button key={l} aria-pressed={lens === l} onClick={() => setLens(l)}>{l.toUpperCase()}</button>)}
      </nav>
      <div className="tools">
        <button className={"askbtn" + (asking ? " on" : "")} onClick={onAsk} title="Ask the copilot (press /)"><span className="askdot" />ASK</button>
        <button className="chip kbd" onClick={onPalette} title="Search agents, days and lenses">⌘K</button>
        <div className="seg" role="group" aria-label="Quality">
          {(["ultra", "high", "lite"] as Tier[]).map(t => (
            <button key={t} aria-pressed={tier === t} disabled={!gl && t !== "lite"} onClick={() => setTier(t)}
              title={t === "ultra" ? "Full effects" : t === "high" ? "Lighter 3D" : "2D view, no 3D"}>{t === "lite" ? "2D" : t.toUpperCase()}</button>
          ))}
        </div>
        <SoundBtn />
        <button className="round" aria-label="How to read" title="How to read" onClick={onHelp}>?</button>
      </div>
    </header>
  );
}

function SoundBtn() {
  const [on, setOn] = useState(soundOn());
  return <button className={"round" + (on ? " sndon" : "")} aria-pressed={on} aria-label={on ? "Sound on" : "Sound off"} title={on ? "Sound on" : "Sound off (default)"}
    onClick={() => { setSound(!on); setOn(!on); }}>{on ? "♪" : "♪̸"}</button>;
}

export function Kpis({ M, i, onPick }: { M: Model; i: number; onPick: (id: string) => void }) {
  const idx = M.index, { agents } = M.rankAt(i), best = agents[0];
  const moved = i > 0 && M.moved;
  const above = M.agents.filter(p => M.gapAt(p, i) > 0).length, total = M.agents.length || 1;
  const band = M.luckAt(i);
  const lucky = band && idx ? M.agents.filter(p => M.gapAt(p, i) > band[1]).length : null;
  const mAbove = M.monkeys.filter(p => M.gapAt(p, i) > 0).length;
  return (
    <section className="kpis" aria-label="At a glance">
      {idx && (
        <button className="kpi glass hot" style={{ textAlign: "left" }} onClick={() => onPick(idx.id)} title="The benchmark: S&P 500 with dividends, in euros. It is the water line.">
          <div className="lbl"><span className="wave" />S&P 500</div>
          <div className={"v num " + tone(M.retAt(idx, i))}>{pct(M.retAt(idx, i))}<small>since {day(idx.from)}</small></div>
        </button>
      )}
      <div className="kpi glass" title="Agents beating the S&P 500 since day zero">
        <div className="lbl">Above water</div>
        <div className="v num">{above}<small>/ {M.agents.length}</small></div>
        <div className="bar"><i style={{ width: `${above / total * 100}%`, background: COLOR.index }} /></div>
      </div>
      {lucky != null ? (
        <div className="kpi glass" title={`Agents doing better than 95% of ${nf(M.luckN)} random monkeys with the same rules. Only these show more than luck.`}>
          <div className="lbl">Above the luck band</div>
          <div className="v num">{lucky}<small>/ {M.agents.length}</small></div>
          <div className="bar"><i style={{ width: `${lucky / total * 100}%`, background: COLOR.luck }} /></div>
        </div>
      ) : (
        <div className="kpi glass" title="Monkeys pick at random. If they beat the index too, beating it proves little.">
          <div className="lbl">Monkeys above water</div>
          <div className="v num">{mAbove}<small>/ {M.monkeys.length}</small></div>
        </div>
      )}
      {best && moved ? (
        <button className="kpi glass hot" style={{ textAlign: "left" }} onClick={() => onPick(best.id)}>
          <div className="lbl"><Shape p={best} />Leader</div>
          <div className="v" style={{ fontSize: 22, fontWeight: 600 }}>{best.name}<small className={"num " + tone(M.gapAt(best, i))}>{pct(M.gapAt(best, i))}</small></div>
        </button>
      ) : (
        <div className="kpi glass"><div className="lbl">Trades this day</div><div className="v num">{(M.A.fillsByDay?.[M.A.meta.dates[i]] || []).length}<small>agents</small></div></div>
      )}
    </section>
  );
}

export function Board({ M, i, open, hover, onPick, onHover }: { M: Model; i: number; open: boolean; hover: string | null; onPick: (id: string) => void; onHover: (id: string | null) => void }) {
  const { agents, rank } = M.rankAt(i);
  const rows = [...agents, ...(M.index ? [M.index] : []), ...(M.equal ? [M.equal] : [])];
  const max = Math.max(1e-4, ...rows.map(p => Math.abs(M.gapAt(p, i))), ...M.monkeys.map(p => Math.abs(M.gapAt(p, i))));
  const mk = M.monkeys.slice().sort((a, b) => M.gapAt(b, i) - M.gapAt(a, i));
  const mid = mk.length ? mk[Math.floor((mk.length - 1) / 2)] : null;
  const band = M.luckAt(i), luckTop = band ? band[1] : null;
  const moved = i > 0 && M.moved;
  const Row = ({ p, cls = "", name = label(p) }: { p: Participant; cls?: string; name?: string }) => {
    const g = M.gapAt(p, i), w = Math.abs(g) / max * 20;
    return (
      <button className={`row ${cls} ${hover === p.id ? "hl" : ""}`} onClick={() => onPick(p.id)} onPointerEnter={() => onHover(p.id)} onPointerLeave={() => onHover(null)}>
        <span className="n num">{rank[p.id] ?? ""}</span><Shape p={p} /><span className="nm">{name}</span>
        {p.type === "index" ? <><span className="trk" /><span className="pc mute">water</span></> : <>
          <span className="trk"><i style={{ [g >= 0 ? "left" : "right"]: "50%", width: w, background: g >= 0 ? COLOR.up : COLOR.down } as React.CSSProperties} /></span>
          <span className={"pc num " + tone(g)}>{moved ? pct(g) : "±0%"}</span></>}
      </button>
    );
  };
  return (
    <aside className={"board glass" + (open ? " open" : "")} aria-label="Ranking">
      <header><span className="lbl">{M.scored && i === M.last ? "Ranking · score" : "Ranking"}</span><span className="lbl">vs S&P 500</span></header>
      <div className="rows">
        {agents.map((p, k) => {
          const next = agents[k + 1];
          const cross = luckTop != null && M.gapAt(p, i) > luckTop && next && M.gapAt(next, i) <= luckTop;
          return <div key={p.id}>
            <Row p={p} />
            {cross && <div className="row" style={{ cursor: "default" }}><span /><span /><span className="luckmark lbl">luck band ↓</span><span /><span /></div>}
          </div>;
        })}
        {M.index && <Row p={M.index} cls="sep ref" />}
        {M.equal && <Row p={M.equal} cls="ref" />}
        {mid && <Row p={mid} cls="ref" name="Monkeys · median" />}
      </div>
    </aside>
  );
}

export function Podium({ M, i, onPick }: { M: Model; i: number; onPick: (id: string) => void }) {
  const { agents, rank } = M.rankAt(i);
  if (!agents.length) return <section className="podium" />;
  if (!(i > 0 && M.moved)) return (
    <section className="podium" aria-label="Podium">
      <span className="lbl">Podium</span>
      <div className="glass" style={{ padding: "13px 20px", textAlign: "center" }}>
        <div style={{ fontWeight: 600 }}>Everyone starts at <span className="num">€{nf(M.A.meta.capital)}</span></div>
        <div className="mute" style={{ fontSize: 12, marginTop: 4 }}>First trades at the next market open</div>
      </div>
    </section>
  );
  const top = [agents[1], agents[0], agents[2]].filter(Boolean);
  const merit = i === M.last && agents.slice(0, 3).some(p => p.merit);
  return (
    <section className="podium" aria-label="Podium">
      <span className={"badge " + (merit ? "merit" : "prov")} title="Merit only after enough history, beating the index and 95% of the monkeys">{merit ? "Merit" : "Provisional"}</span>
      <div className="steps">
        {top.map(p => (
          <button key={p.id} className={`step glass hot p${rank[p.id]}`} onClick={() => onPick(p.id)}>
            <div className="who"><Shape p={p} />{p.name}</div>
            <div className={"pct num " + tone(M.gapAt(p, i))}>{pct(M.gapAt(p, i))}</div>
            <div className="base">{rank[p.id]}</div>
          </button>
        ))}
      </div>
    </section>
  );
}

// Time Machine: drag to any night; play the season; bookmarks on key days.
export function TimeMachine({ M, i, setI, playing, setPlaying }: { M: Model; i: number; setI: (n: number) => void; playing: boolean; setPlaying: (b: boolean) => void }) {
  const n = M.A.meta.dates.length;
  const [speed, setSpeed] = useState(1);
  const ref = useRef(i); ref.current = i;
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      const k = ref.current + 1;
      if (k > M.last) { setPlaying(false); return; }
      tick(); setI(k);
    }, 520 / speed);
    return () => clearInterval(t);
  }, [playing, speed, M.last, setI, setPlaying]);
  if (n < 2) return null;
  const marks = M.A.meta.marks || [];
  return (
    <section className="tm glass" aria-label="Time Machine">
      <button className="round play" aria-label={playing ? "Pause" : "Play the season"} onClick={() => { if (!playing && i >= M.last) setI(0); setPlaying(!playing); }}>{playing ? "❚❚" : "▶"}</button>
      <button className="chip speed" onClick={() => setSpeed(s => s === 1 ? 4 : s === 4 ? 12 : 1)} title="Speed">{speed}×</button>
      <div className="track">
        <input type="range" min={0} max={M.last} value={i} aria-label="Day" onChange={e => { setPlaying(false); setI(+e.target.value); }} />
        {marks.map(m => {
          const k = M.A.meta.dates.indexOf(m.d); if (k < 0) return null;
          // pointer shortcut only (keyboard: the same days are in ⌘K search and the arrow keys)
          return <span key={m.d + m.k} aria-hidden="true" className={"mark-t " + m.k} style={{ left: `${k / M.last * 100}%` }} title={`${day(m.d)} · ${m.label}`} onClick={() => { setPlaying(false); setI(k); }} />;
        })}
        <div className="ends num"><span>{day(M.A.meta.dates[0])}</span><span>{day(M.A.meta.dates[M.last])}</span></div>
      </div>
      <span className="num tm-day">{day(M.A.meta.dates[i])}</span>
      <button className={"chip" + (i === M.last ? " on" : "")} onClick={() => { setPlaying(false); setI(M.last); }}>LIVE</button>
    </section>
  );
}

export function Legend({ M }: { M: Model }) {
  return (
    <div className="legend glass">
      {M.species.map(s => <span key={s}><span className="gem" style={{ background: SPECIES_COLOR[s] || "#9aa4b8" }} />{M.A.species[s].label}</span>)}
      <span><span className="dot" style={{ background: COLOR.monkey }} />Monkeys</span>
      <span><span className="dot" style={{ border: "2px solid #fff" }} />Equal</span>
      <span><span className="wave" />S&P 500</span>
      <span title={`90% of ${nf(M.luckN)} random monkeys end up inside it`}><span className="dot" style={{ background: COLOR.luck, opacity: .5, borderRadius: 2 }} />Luck band</span>
    </div>
  );
}

export function Tip({ M, i, tip }: { M: Model; i: number; tip: TipState }) {
  if (!tip) return null;
  const p = M.byId[tip.id]; if (!p) return null;
  const x = Math.min(tip.x, innerWidth - 300), y = Math.min(tip.y, innerHeight - 90);
  return (
    <div className="tip" style={{ left: x, top: y }}>
      <b>{label(p)}</b>{p.type === "agent" && p.sp && <span className="mute"> · {M.A.species[p.sp]?.label}</span>}<br />
      <span className="num">€{nf(M.valueAt(p, i))}</span> · <span className={"num " + tone(M.retAt(p, i))}>{pct(M.retAt(p, i))}</span>
      {p.type !== "index" && <> · vs index <span className={"num " + tone(M.gapAt(p, i))}>{pct(M.gapAt(p, i))}</span></>}
      {i === M.last && p.pctAll != null && <> · beats <span className="num">{nf(p.pctAll * 100)}%</span> of monkeys</>}
    </div>
  );
}

// Command palette (Ctrl/⌘ + K): agents, days and lenses.
export function Palette({ M, onClose, onPick, setI, setLens }: { M: Model; onClose: () => void; onPick: (id: string) => void; setI: (n: number) => void; setLens: (l: Lens) => void }) {
  const [q, setQ] = useState(""), [sel, setSel] = useState(0);
  const items = useMemo(() => {
    const all: { k: string; label: string; sub: string; run: () => void }[] = [
      { k: "lens", label: "Today", sub: "lens", run: () => setLens("today") },
      { k: "lens", label: "Arena", sub: "lens", run: () => setLens("arena") },
      { k: "lens", label: "Evolution", sub: "lens", run: () => setLens("evolution") },
      { k: "lens", label: "Journal", sub: "lens", run: () => setLens("journal") },
      { k: "lens", label: "World", sub: "lens", run: () => setLens("world") },
      { k: "lens", label: "Network", sub: "lens", run: () => setLens("network") },
      { k: "lens", label: "Lab", sub: "lens", run: () => setLens("lab") },
      { k: "lens", label: "People", sub: "lens", run: () => setLens("people") },
      { k: "day", label: "Live (latest night)", sub: day(M.A.meta.dates[M.last]), run: () => { setLens("arena"); setI(M.last); } },
      ...M.order.map(p => ({ k: "p", label: label(p), sub: p.type === "agent" ? M.A.species[p.sp || ""]?.label || "" : p.type, run: () => onPick(p.id) })),
      ...(M.A.meta.marks || []).map(m => ({ k: "day", label: m.label, sub: day(m.d), run: () => { setLens("arena"); setI(M.A.meta.dates.indexOf(m.d)); } })),
      ...M.A.meta.dates.map((d, k) => ({ k: "day", label: dayY(d), sub: `day ${k}`, run: () => { setLens("arena"); setI(k); } })),
    ];
    const s = q.trim().toLowerCase();
    return (s ? all.filter(x => (x.label + " " + x.sub).toLowerCase().includes(s)) : all.slice(0, 12)).slice(0, 12);
  }, [q, M, onPick, setI, setLens]);
  const go = (k: number) => { const it = items[k]; if (it) { it.run(); onClose(); } };
  return (
    <div className="veil top-veil" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette glass" role="dialog" aria-label="Search">
        <input autoFocus placeholder="Agent, day, lens…" value={q} onChange={e => { setQ(e.target.value); setSel(0); }}
          onKeyDown={e => { if (e.key === "ArrowDown") { e.preventDefault(); setSel(s => Math.min(s + 1, items.length - 1)); } if (e.key === "ArrowUp") { e.preventDefault(); setSel(s => Math.max(s - 1, 0)); } if (e.key === "Enter") go(sel); }} />
        <ul>{items.map((it, k) => <li key={it.k + it.label + it.sub} className={k === sel ? "sel" : ""} onMouseEnter={() => setSel(k)} onClick={() => go(k)}><span>{it.label}</span><span className="mute num">{it.sub}</span></li>)}</ul>
      </div>
    </div>
  );
}

export function Help({ M, onClose, onTour }: { M: Model; onClose: () => void; onTour?: () => void }) {
  return (
    <div className="veil" onClick={onClose}>
      <div className="help glass" role="dialog" aria-modal="true" aria-label="How to read">
        <h2>How to read the arena {onTour && <button className="chip on" style={{ marginLeft: 12, cursor: "pointer" }} onClick={e => { e.stopPropagation(); onTour(); }}>▶ 20-second tour</button>}</h2>
        <div><span className="ic"><span className="gem" style={{ background: SPECIES_COLOR.arrow }} /></span><span><b>Each crystal is an agent</b>Colour = species. Bigger = more money. Glowing = traded at that day's open.</span></div>
        <div><span className="ic"><span className="wave" /></span><span><b>The water is the S&P 500</b>Above the water = beating the index. Below = losing to it.</span></div>
        <div><span className="ic"><span className="dot" style={{ background: COLOR.luck }} /></span><span><b>The grey band is luck</b>{nf(M.luckN)} monkeys follow the same rules but pick at random; 90% end inside the band. Only agents above it show more than luck.</span></div>
        <div><span className="ic">⏵</span><span><b>Time Machine</b>Drag the timeline or press play: the whole arena replays any night exactly as it was.</span></div>
        <div><span className="ic">?</span><span><b>Why? and Verify</b>In a card, tap any trade: see what drove it, and recompute it in your browser from that night's readings.</span></div>
        <div><span className="ic">⌘K</span><span><b>Search</b>Jump to any agent, day or lens.</span></div>
        <div><span className="ic">/</span><span><b>ASK</b>Ask in any language, typed or spoken. Answers only from the archive, with sources; can also move the arena for you.</span></div>
        <p>Each agent starts with €{nf(M.A.meta.capital)} of simulated money on the S&P 100. Decisions at night, filled at the next open, with real costs. Not investment advice. Rules v{M.A.meta.rules} · engine {M.A.meta.engine}.</p>
      </div>
    </div>
  );
}
