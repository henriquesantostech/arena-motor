import { useEffect, useRef, useState } from "react";
import { COLOR, colorOf, day, dayY, eur, label, nf, pct, tick, tone, type Model, type Participant } from "../data";
import { Shape } from "../hud";

function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [s, setS] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver(() => setS({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el); return () => ro.disconnect();
  }, []);
  return [ref, s] as const;
}

export function AgentCard({ M, p, onClose, onGo }: { M: Model; p: Participant; onClose: () => void; onGo: (id: string) => void }) {
  const isAgent = p.type === "agent";
  const sp = p.sp ? M.A.species[p.sp] : null;
  const i = M.order.indexOf(p);
  const step = (k: number) => onGo(M.order[(i + k + M.order.length) % M.order.length].id);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus({ preventScroll: true });
    const k = (e: KeyboardEvent) => { if (e.key === "ArrowRight") step(1); if (e.key === "ArrowLeft") step(-1); };
    addEventListener("keydown", k); return () => removeEventListener("keydown", k);
  });
  const sub = isAgent ? `${sp?.label} · ${sp?.about}` : p.type === "monkey" ? "Control · picks at random" : p.type === "index" ? "Benchmark · the water line" : "Benchmark · all companies, equal parts";
  const L = M.A.luck;
  const tiles: [string, string, string, string?][] = [
    ["Value", eur(p.value), ""],
    ["Return", pct(p.ret, 2), tone(p.ret)],
    ["vs S&P 500", p.type === "index" ? "—" : pct(p.vsIdx, 2), tone(p.vsIdx)],
    p.pctAll != null && L
      ? [`Beats ${nf(L.n)} monkeys`, nf(p.pctAll * 100) + "%", p.pctAll >= .95 ? "up" : "", `Better than ${nf(p.pctAll * 100)}% of all random monkeys; ${nf((p.pctMirror || 0) * 100)}% of those copying its rules`]
      : ["Beats monkeys", isAgent || p.type === "equal" ? (p.beatsMonkeys == null ? "—" : nf(p.beatsMonkeys * 100) + "%") : "—", ""],
    ["Worst drop", p.mdd ? pct(-p.mdd, 1) : "0%", p.mdd > 1e-4 ? "down" : ""],
    [isAgent ? "Rank · score" : "Days", isAgent ? `#${M.rank[p.id]}${p.score != null ? " · " + nf(p.score, 2) : ""}` : nf(p.days), "", "Score = return over the index per unit of extra risk"],
  ];
  return (
    <div className="veil" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <article className="sheet glass" role="dialog" aria-modal="true" aria-label={label(p)}>
        <div className="hd" style={{ color: colorOf(p) }}>
          {isAgent ? <span className="gem" style={{ background: colorOf(p) }} /> : <Shape p={p} />}
          <div style={{ color: "var(--text)" }}><h1>{label(p)}</h1><div className="sub">{sub}</div></div>
          {isAgent && <span className={"badge " + (p.merit ? "merit" : "prov")}>{p.merit ? "Merit" : "Provisional"}</span>}
        </div>
        <div className="nav">
          <button aria-label="Previous" onClick={() => step(-1)}>‹</button>
          <button aria-label="Next" onClick={() => step(1)}>›</button>
          <button aria-label="Close" ref={closeRef} onClick={onClose}>✕</button>
        </div>
        <div className="tiles6">
          {tiles.map(([l, v, c, t]) => <div key={l} className="tile6" title={t}><div className="lbl">{l}</div><div className={"v num " + c}>{v}</div></div>)}
        </div>
        <section className="pane chart">
          <header><span className="lbl">Since day zero</span>
            <span className="k"><span><span className="dot" style={{ background: colorOf(p) }} />{label(p)}</span>
              {p.type !== "index" && <span><span className="dot" style={{ background: COLOR.index }} />S&P 500</span>}
              <span title={L ? `90% of ${nf(L.n)} random monkeys end up in this band` : "Range of the live monkeys"}><span className="dot" style={{ background: COLOR.luck, opacity: .6 }} />Luck band</span></span>
          </header>
          <Chart M={M} p={p} />
        </section>
        <section className="pane dna">
          {isAgent && p.dna ? <>
            <header><span className="lbl">DNA · what it values</span>
              <span className="k num">{p.dna.picks} stocks · {p.dna.review}d review · {p.dna.stop ? "stop " + pct(-p.dna.stop, 0) : "no stop"}</span></header>
            <Radar p={p} />
          </> : <>
            <header><span className="lbl">How it works</span></header>
            <div className="mute" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
              {p.type === "monkey" ? <>Same rules as <b style={{ color: "var(--text)" }}>{p.copies || "an agent"}</b> (how many stocks, when to review, when to cut), but every pick is random. If an agent cannot beat its monkeys, its skill is luck.</>
                : p.type === "index" ? "The S&P 500 with dividends, in euros, bought on day zero with the same costs. Agents above the water are beating it."
                  : "Equal parts in every company of the universe, never touched. Shows whether picking companies adds anything."}
            </div>
          </>}
        </section>
        <section className="pane holdings">
          <header><span className="lbl">Holdings · {p.hold.length}</span><span className="k">size = weight · colour = gain</span></header>
          {p.hold.length ? <Tiles p={p} /> : <div className="empty">All in cash</div>}
        </section>
        <section className="pane moves">
          <header><span className="lbl">Latest moves</span><span className="k">decided at night · filled at the next open</span></header>
          <div className="fill" style={{ overflow: "hidden" }}>
            {[...p.next.map(o => ({ d: "next", k: "next", side: o.k, t: o.t, eur: o.eur, why: o.why, ratio: undefined as number | undefined })), ...p.log.map(l => ({ ...l, side: l.k }))]
              .slice(0, 14).map((l, j) => (
                <div className="mv" key={j}>
                  <span className="mute num">{l.d === "next" ? "Next" : day(l.d)}</span>
                  <span className={"k-" + l.k}>{l.k === "next" ? l.side : l.k}</span>
                  <b>{tick(l.t)}</b>
                  <span className="num">{l.eur != null ? eur(l.eur) : l.ratio ? "×" + l.ratio : ""}</span>
                  <span className="why" title={l.why || ""}>{l.why || ""}</span>
                </div>
              ))}
            {!p.next.length && !p.log.length && <div className="empty">No moves yet. Orders are placed at night and filled at the next open.</div>}
          </div>
        </section>
        <div className="foot">
          <span>Volatility <b>{pct(p.vol, 1, false)}</b></span><span>Fees <b>{eur(p.fees, 2)}</b></span><span>Dividends <b>{eur(p.divs, 2)}</b></span>
          <span>Turnover <b>{p.turnover != null ? nf(p.turnover, 1) + "×/yr" : "—"}</b></span><span>Win rate <b>{p.hit == null ? "—" : pct(p.hit, 0, false)}</b></span>
          <span>Est. tax <b>{eur(p.tax)}</b></span><span>Born <b>{dayY(p.born)}</b></span><span>Cash <b>{eur(p.cash)}</b></span>
        </div>
      </article>
    </div>
  );
}

function Chart({ M, p }: { M: Model; p: Participant }) {
  const [ref, { w: W, h: H }] = useSize<HTMLDivElement>();
  const dates = M.A.meta.dates, o = Math.max(0, dates.indexOf(p.from));
  const base = p.s[0] || 1, mine = p.s.map(v => v / base - 1);
  const ix = M.index && p.type !== "index" ? M.index.s.slice(o).map((v, _i, a) => v / a[0] - 1) : [];
  const cap = M.A.meta.capital;
  const band = M.A.luck?.s ? M.A.luck.s.slice(o) : (M.A.band || []).slice(o).map(b => b && [b[0] / cap - 1, b[1] / cap - 1] as [number, number]);
  const m = { l: 46, r: 8, t: 8, b: 20 };
  let svg = null;
  if (W > 0 && H > 0) {
    const all = [0, ...mine, ...ix, ...band.flat().filter((v): v is number => v != null)];
    let lo = Math.min(...all), hi = Math.max(...all); if (hi - lo < .01) { hi += .005; lo -= .005; }
    const pad = (hi - lo) * .08; lo -= pad; hi += pad;
    const n = Math.max(mine.length, 2);
    const X = (i: number) => m.l + (W - m.l - m.r) * (i / (n - 1)), Y = (v: number) => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
    const line = (a: number[]) => a.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
    const bf = band.map((b, i) => b ? [i, b] as const : null).filter(Boolean) as (readonly [number, [number, number]])[];
    // drawdown shadow under the line
    let peak = -Infinity; const dd = mine.map(v => { peak = Math.max(peak, v); return peak; });
    const col = colorOf(p);
    svg = (
      <svg viewBox={`0 0 ${W} ${H}`}>
        <defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={col} stopOpacity=".35" /><stop offset="1" stopColor={col} stopOpacity="0" /></linearGradient></defs>
        {[lo + pad, 0, hi - pad].map((v, k) => <g key={k}><line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke={`rgba(130,160,220,${v === 0 ? .3 : .1})`} />
          <text x={m.l - 6} y={Y(v) + 4} textAnchor="end" fill="#56627d" fontSize="10.5" fontFamily="var(--num)">{pct(v, 1)}</text></g>)}
        {bf.length > 1 && <polygon fill={COLOR.luck} opacity=".14" points={bf.map(([i, b]) => `${X(i)},${Y(b[1])}`).join(" ") + " " + bf.slice().reverse().map(([i, b]) => `${X(i)},${Y(b[0])}`).join(" ")} />}
        {mine.length > 1 && <polygon fill="rgba(255,107,107,.12)" points={dd.map((v, i) => `${X(i)},${Y(v)}`).join(" ") + " " + mine.map((v, i) => [i, v] as const).reverse().map(([i, v]) => `${X(i)},${Y(v)}`).join(" ")} />}
        {ix.length > 1 && <polyline points={line(ix)} fill="none" stroke={COLOR.index} strokeWidth="1.6" strokeDasharray="4 3" />}
        {mine.length > 1 && <polygon points={line(mine) + ` ${X(mine.length - 1)},${H - m.b} ${X(0)},${H - m.b}`} fill="url(#cg)" opacity=".5" />}
        {mine.length > 1 ? <polyline points={line(mine)} fill="none" stroke={col} strokeWidth="2.4" strokeLinejoin="round" style={{ filter: `drop-shadow(0 0 6px ${col})` }} />
          : <text x={(W + m.l) / 2} y={H / 2} textAnchor="middle" fill="#56627d" fontSize="12">The line starts after the first trading day</text>}
        {[0, n - 1].map(i => dates[o + i] && <text key={i} x={X(i)} y={H - 4} textAnchor={i ? "end" : "start"} fill="#56627d" fontSize="10.5">{day(dates[o + i])}</text>)}
      </svg>
    );
  }
  return <div className="fill" ref={ref}>{svg}</div>;
}

function Radar({ p }: { p: Participant }) {
  const [ref, { w: W, h: H }] = useSize<HTMLDivElement>();
  const w = p.dna!.w, keys = Object.keys(w), N = keys.length;
  if (!(W > 0 && H > 0)) return <div className="fill" ref={ref} />;
  const cx = W / 2, cy = H / 2 + 2, R = Math.min(W * .32, H / 2 - 18), mx = Math.max(1, ...keys.map(k => w[k]));
  const pt = (i: number, r: number) => [cx + Math.sin(i / N * Math.PI * 2) * r, cy - Math.cos(i / N * Math.PI * 2) * r];
  const c = colorOf(p);
  return (
    <div className="fill" ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`}>
        {[.33, .66, 1].map(f => <polygon key={f} points={keys.map((_, i) => pt(i, R * f).join(",")).join(" ")} fill="none" stroke="rgba(130,160,220,.14)" />)}
        {keys.map((k, i) => {
          const [x, y] = pt(i, R), [lx, ly] = pt(i, R + 12), on = w[k] > 0;
          return <g key={k}><line x1={cx} y1={cy} x2={x} y2={y} stroke="rgba(130,160,220,.1)" />
            <text x={lx} y={ly + 3} fontSize="10" fill={on ? "#c9d4ec" : "#3f4a63"} textAnchor={Math.abs(lx - cx) < 6 ? "middle" : lx > cx ? "start" : "end"}>{k}{on ? ` ${w[k]}` : ""}</text></g>;
        })}
        <polygon points={keys.map((k, i) => pt(i, R * w[k] / mx).join(",")).join(" ")} fill={c} fillOpacity=".22" stroke={c} strokeWidth="2" strokeLinejoin="round" style={{ filter: `drop-shadow(0 0 8px ${c})` }} />
      </svg>
    </div>
  );
}

function Tiles({ p }: { p: Participant }) {
  const [ref, { w: W, h: H }] = useSize<HTMLDivElement>();
  const out: [{ t: string; name: string; w: number; gain: number | null }, number, number, number, number][] = [];
  if (W > 0 && H > 0) {
    const items = p.hold.filter(h => h.w > 0).map(h => ({ h: { t: h.t, name: h.name, w: h.w, gain: h.gain }, a: h.w }));
    const cash = p.cash / (p.value || 1);
    if (cash > .005) items.push({ h: { t: "Cash", name: "Uninvested cash", w: cash, gain: null }, a: cash });
    const tot = items.reduce((s, i) => s + i.a, 0) || 1;
    items.forEach(i => i.a = i.a / tot * W * H);
    const lay = (list: typeof items, x: number, y: number, w: number, h: number): void => {
      if (!list.length) return;
      if (list.length === 1) { out.push([list[0].h, x, y, w, h]); return; }
      const sum = list.reduce((s, i) => s + i.a, 0);
      let acc = list[0].a, k = 1;
      while (k < list.length - 1 && acc + list[k].a <= sum / 2) acc += list[k++].a;
      const f = acc / sum;
      if (w >= h) { lay(list.slice(0, k), x, y, w * f, h); lay(list.slice(k), x + w * f, y, w * (1 - f), h); }
      else { lay(list.slice(0, k), x, y, w, h * f); lay(list.slice(k), x, y + h * f, w, h * (1 - f)); }
    };
    lay(items, 0, 0, W, H);
  }
  const bg = (g: number | null) => g == null ? "rgba(255,255,255,.05)" : g >= 0 ? `rgba(62,224,143,${.12 + Math.min(g / .15, 1) * .5})` : `rgba(255,107,107,${.12 + Math.min(-g / .15, 1) * .5})`;
  return (
    <div className="fill" ref={ref}>
      <div className="mtiles">
        {out.map(([h, x, y, w, hh]) => (
          <div key={h.t} className="mt" style={{ left: x, top: y, width: w, height: hh, background: bg(h.gain) }}
            title={`${h.name} · ${pct(h.w, 1, false)}${h.gain != null ? " · " + pct(h.gain, 1) + " since bought" : ""}`}>
            {w > 30 && hh > 16 && <b>{tick(h.t)}</b>}
            {w > 56 && hh > 34 && <span className="num">{pct(h.w, 0, false)}{h.gain != null && <> · <i style={{ fontStyle: "normal" }} className={tone(h.gain)}>{pct(h.gain, 1)}</i></>}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
