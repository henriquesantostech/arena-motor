// Story → Detail panel, shared by both prototypes. Slides in from the right; Evidence links to the current site.
import { useEffect, useRef, useState } from "react";
import type { Model, Participant } from "../data";
import { bodyPath, capital, caresAbout, company, creatureFill, creatureOf, dayName, euro, sentence, STRATEGY } from "./common";

export function CreatureSvg({ p, size, dark, t = 0 }: { p: Participant; size: number; dark: boolean; t?: number }) {
  const c = creatureOf(p), r = size * 0.32;
  return (
    <svg width={size} height={size} viewBox={`${-size / 2} ${-size / 2} ${size} ${size}`} aria-hidden="true">
      <path d={bodyPath(c, r, t)} fill={creatureFill(c, dark)} />
      {!c.stone && <><circle cx={r * 0.55 * c.elong} cy={-r * 0.18} r={Math.max(1.2, r * 0.11)} fill={dark ? "#0b0f19" : "#fff"} />
        <circle cx={r * 0.55 * c.elong + r * .03} cy={-r * 0.18} r={Math.max(.6, r * 0.05)} fill={dark ? "#fff" : "#1b2030"} /></>}
    </svg>
  );
}

export function useClock(on = true) {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (!on || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0; const t0 = performance.now();
    const f = () => { setT((performance.now() - t0) / 1000); raf = requestAnimationFrame(f); };
    raf = requestAnimationFrame(f); return () => cancelAnimationFrame(raf);
  }, [on]);
  return t;
}

export function Story({ M, p, i, dark, onClose, crumbs }: { M: Model; p: Participant; i: number; dark: boolean; onClose: () => void; crumbs: string[] }) {
  const [detail, setDetail] = useState(false);
  const t = useClock();
  const A = M.A, cap = capital(A), idx = M.index;
  const v = p.dead ? p.value : M.valueAt(p, i), gapEur = (M.gapAt(p, i)) * cap;
  const ref = useRef<HTMLElement>(null);
  useEffect(() => { setDetail(false); ref.current?.scrollTo({ top: 0 }); }, [p.id]);
  const moves = p.log.filter(m => m.k === "buy" || m.k === "sell");
  const strategy = p.dead ? `Died on ${dayName(p.dead.died)}: ranked ${p.dead.rank} of ${p.dead.of} at a selection.` : STRATEGY[p.sp || ""] || "";
  return (
    <aside className="story" ref={ref} aria-label={p.name}>
      <nav className="crumbs">{crumbs.map((c, k) => <span key={k}>{c}</span>)}<span>{p.name}</span><button className="x" onClick={onClose} aria-label="Back">✕</button></nav>
      <div className="hero">
        <CreatureSvg p={p} size={120} dark={dark} t={t} />
        <div>
          <h2>{p.name}</h2>
          <p className="lead">{strategy}</p>
        </div>
      </div>
      <p className="answer">
        {euro(cap)} became <b className="num">{euro(v)}</b>.{" "}
        {idx && <>That is <b className={"num " + (gapEur >= 0 ? "gain" : "loss")}>{euro(Math.abs(gapEur))} {gapEur >= 0 ? "more" : "less"}</b> than just buying the market.</>}
      </p>
      <MiniLine M={M} p={p} i={i} />
      <h3>Latest decisions</h3>
      <ul className="sentences">{moves.slice(0, detail ? 20 : 3).map((m, k) => <li key={k}><span className="when">{dayName(m.d)}</span>{sentence(A, m)}</li>)}
        {!moves.length && <li className="quiet">No trades yet.</li>}</ul>
      {!detail ? <button className="more" onClick={() => setDetail(true)}>See everything it owns and why ↓</button> : <>
        <h3>What it owns</h3>
        <div className="owns">{p.hold.slice(0, 16).map(h => <div key={h.t} className="own" style={{ flexGrow: Math.max(1, h.w * 100) }}>
          <b>{company(A, h.t)}</b><span className="num">{euro(h.eur)}{h.gain != null && <span className={h.gain >= 0 ? "gain" : "loss"}> {h.gain >= 0 ? "▲" : "▼"}</span>}</span></div>)}
          {!p.hold.length && <div className="quiet">Only cash.</div>}</div>
        {p.dna && <><h3>What it cares about</h3>
          <ul className="cares">{caresAbout(p).map(r => <li key={r.label}><span>{r.label}</span><span className="dots">{"●●●●●".slice(0, r.dots)}<span className="off">{"●●●●●".slice(r.dots)}</span></span></li>)}</ul></>}
        <a className="evidence-link" href={`../../#/${p.id}`}>Check the evidence: every number, verified →</a>
      </>}
    </aside>
  );
}

function MiniLine({ M, p, i }: { M: Model; p: Participant; i: number }) {
  const dates = M.A.meta.dates, o = Math.max(0, dates.indexOf(p.from));
  const n = Math.min(p.s.length, i - o + 1);
  if (n < 2) return <div className="mini quiet">The line starts after the first trading day.</div>;
  const mine = p.s.slice(0, n).map(v => v / p.s[0] - 1);
  const mk = M.index ? M.index.s.slice(o, o + n).map((v, _k, a) => v / a[0] - 1) : [];
  const all = [...mine, ...mk, 0], lo = Math.min(...all), hi = Math.max(...all), W = 320, H = 90;
  const X = (k: number) => (k / (n - 1)) * W, Y = (v: number) => 6 + (H - 12) * (1 - (v - lo) / ((hi - lo) || 1));
  const line = (a: number[]) => a.map((v, k) => `${X(k).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  return (
    <svg className="mini" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${p.name} against the market`}>
      <line x1="0" x2={W} y1={Y(0)} y2={Y(0)} className="zero" />
      {mk.length > 1 && <polyline points={line(mk)} className="mkt" />}
      <polyline points={line(mine)} className="me" />
    </svg>
  );
}
