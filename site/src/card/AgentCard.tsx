import { useEffect, useMemo, useRef, useState } from "react";
import {
  COLOR, colorOf, day, dayY, eur, label, loadShard, nf, pct, sigLabel, tick, tone, verify,
  type Model, type Move, type Participant, type Reason, type Shard, type Verdict,
} from "../data";
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

type Decision = Move & { next?: boolean };

export function AgentCard({ M, p, at, onClose, onGo }: { M: Model; p: Participant; at: number; onClose: () => void; onGo: (id: string) => void }) {
  const isAgent = p.type === "agent";
  const sp = p.sp ? M.A.species[p.sp] : null;
  const i = M.order.indexOf(p);
  const step = (k: number) => onGo(M.order[(i + k + M.order.length) % M.order.length].id);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [why, setWhy] = useState<Decision | null>(null);
  useEffect(() => { setWhy(null); }, [p.id]);
  useEffect(() => {
    closeRef.current?.focus({ preventScroll: true });
    const k = (e: KeyboardEvent) => { if (why) return; if (e.key === "ArrowRight") step(1); if (e.key === "ArrowLeft") step(-1); };
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
  const decisions: Decision[] = [
    ...p.next.map(o => ({ d: M.A.meta.updated || "", dd: o.dd, k: o.k, t: o.t, eur: o.eur, why: o.why, r: o.r, next: true })),
    ...p.log,
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
          <Chart M={M} p={p} at={at} decisions={decisions} onWhy={setWhy} />
        </section>
        <section className="pane dna">
          {isAgent && p.dna ? <>
            <header><span className="lbl">DNA</span>
              <span className="k num">{p.dna.picks} stocks · {p.dna.review}d review · {p.dna.stop ? "stop " + pct(-p.dna.stop, 0) : "no stop"}{p.dna.band != null ? ` · band ${p.dna.band}` : ""}</span></header>
            <Helix M={M} p={p} />
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
          <header><span className="lbl">Decisions</span><span className="k">tap one: why, and verify it</span></header>
          <div className="fill" style={{ overflow: "hidden" }}>
            {decisions.slice(0, 14).map((l, j) => (
              <button className={"mv" + (l.r ? " can" : "")} key={j} onClick={() => l.r && setWhy(l)} disabled={!l.r} title={l.why || ""}>
                <span className="mute num">{l.next ? "Next" : day(l.d)}</span>
                <span className={"k-" + (l.next ? "next" : l.k)}>{l.k}</span>
                <b>{tick(l.t)}</b>
                <span className="num">{l.eur != null ? eur(l.eur) : l.ratio ? "×" + l.ratio : ""}</span>
                <span className="why">{l.r?.score != null ? <><span className="num">score {nf(l.r.score, 2)}</span> · <span className="num">#{l.r.rank}/{l.r.of}</span> · {causeLabel(l.r)}</> : l.why || ""}</span>
              </button>
            ))}
            {!decisions.length && <div className="empty">No moves yet. Orders are placed at night and filled at the next open.</div>}
          </div>
        </section>
        <div className="foot">
          <span>Volatility <b>{pct(p.vol, 1, false)}</b></span><span>Fees <b>{eur(p.fees, 2)}</b></span><span>Dividends <b>{eur(p.divs, 2)}</b></span>
          <span>Turnover <b>{p.turnover != null ? nf(p.turnover, 1) + "×/yr" : "—"}</b></span><span>Win rate <b>{p.hit == null ? "—" : pct(p.hit, 0, false)}</b></span>
          <span>Est. tax <b>{eur(p.tax)}</b></span><span>Born <b>{dayY(p.born)}</b></span><span>Cash <b>{eur(p.cash)}</b></span>
        </div>
        {why && <Why M={M} p={p} d={why} onClose={() => setWhy(null)} />}
      </article>
    </div>
  );
}

const causeLabel = (r: Reason) => ({ entry: "entry", swap: "replaced", stop_loss: "stop loss", rank_band: "left the top band", rebalance: "rebalance", delisting: "delisted" } as Record<string, string>)[r.cause || ""] || r.cause || "";

// ---------- Why? waterfall + evidence chain + Verify ----------
function Why({ M, p, d, onClose }: { M: Model; p: Participant; d: Decision; onClose: () => void }) {
  const [sh, setSh] = useState<Shard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [v, setV] = useState<Verdict | null>(null);
  const [busy, setBusy] = useState(false);
  const night = d.dd || null;
  useEffect(() => { setSh(null); setV(null); setErr(null); if (night) loadShard(night).then(setSh).catch(() => setErr("readings unavailable")); }, [night]);
  const w = p.dna?.w || {};
  const r = d.r || {};
  const monkey = p.type === "monkey";
  const terms = useMemo(() => {
    if (!sh || monkey) return null;
    const z = sh.sig.z[d.t]; if (!z) return null;
    return sh.sig.cols.map((c, k) => ({ s: c, z: z[k], w: w[c] || 0, term: z[k] * (w[c] || 0) / 100, raw: sh.sig.raw[d.t]?.[k] ?? null })).filter(x => x.w).sort((a, b) => Math.abs(b.term) - Math.abs(a.term));
  }, [sh, d.t, w, monkey]);
  const run = async () => { if (!sh) return; setBusy(true); try { setV(await verify(sh, w, d.t, r)); } finally { setBusy(false); } };
  const evid = M.A.meta.evidence || {};
  return (
    <div className="why glass" role="dialog" aria-label="Why this decision">
      <header>
        <div><span className={"k-" + d.k}>{d.k}</span> <b className="t">{tick(d.t)}</b> <span className="mute">{d.next ? "at the next open" : "filled " + dayY(d.d)} · decided the night of {dayY(night)}</span></div>
        <button className="x" aria-label="Back" onClick={onClose}>✕</button>
      </header>
      <div className="whygrid">
        <section>
          <div className="lbl">Why? · how each signal pushed the score</div>
          {monkey ? <div className="mute pad">Random pick: tonight's draw from the seed <span className="num">{r.seed ? String(r.seed).slice(0, 12) + "…" : "—"}</span>. No signal is used, by design.</div>
            : terms ? <Waterfall terms={terms} score={r.score ?? terms.reduce((s, x) => s + x.term, 0)} A={M.A} color={colorOf(p)} evid={evid} />
              : <div className="mute pad">{err || (night ? "Loading that night's readings…" : "No decision night on record (e.g. day-zero entries).")}</div>}
          <div className="facts num">
            {r.score != null && <span>score <b>{nf(r.score, 4)}</b></span>}
            {r.rank != null && <span>rank <b>#{r.rank}</b> of {r.of}</span>}
            {r.cause && <span>cause <b>{causeLabel(r)}</b></span>}
          </div>
          <div className="mute small">{d.why}</div>
        </section>
        <section>
          <div className="lbl">Evidence chain</div>
          <ol className="chain">
            <li><b>Decision</b><span>{causeLabel(r) || d.k} {tick(d.t)} · score {nf(r.score, 4)} · rank {r.rank ?? "—"}/{r.of ?? "—"}</span></li>
            <li><b>Readings</b><span>{sh ? `${Object.keys(sh.sig.z).length} companies × ${sh.sig.cols.length} signals, night of ${day(night)}` : "—"}</span><code title="SHA-256 of the readings">{sh ? sh.sig.sha256.slice(0, 16) + "…" : ""}</code></li>
            <li><b>Data cut-off</b><span>{String(sh?.inputs?.cutoff ?? "—")}</span></li>
            <li><b>Source files</b><span>{sh?.inputs ? Object.entries(sh.inputs).filter(([k, x]) => typeof x === "string" && k !== "cutoff").map(([k, x]) => <code key={k} title={k + ": " + x}>{k} {String(x).slice(0, 10)}…</code>) : "—"}</span></li>
            <li><b>Journal</b><span>{sh?.version ? `engine ${sh.version.engine} · rules ${sh.version.rules}` : ""}</span><code title="SHA-256 of the night's journal file">{sh?.journalSha256 ? sh.journalSha256.slice(0, 16) + "…" : ""}</code></li>
          </ol>
          {!monkey && r.score != null && (
            <div className="verify">
              <button className={"vbtn" + (v ? (v.hashOk && v.scoreOk && v.rankOk ? " ok" : " bad") : "")} onClick={run} disabled={!sh || busy}>
                {busy ? "Verifying…" : v ? (v.hashOk && v.scoreOk && v.rankOk ? "✓ Verified" : "✗ Mismatch") : "Verify"}
              </button>
              {v ? <ul className="checks num">
                <li className={v.hashOk ? "up" : "down"}>{v.hashOk ? "✓" : "✗"} readings hash {v.hash.slice(0, 12)}…</li>
                <li className={v.scoreOk ? "up" : "down"}>{v.scoreOk ? "✓" : "✗"} score recomputed {nf(v.score, 4)} (stored {nf(r.score, 4)})</li>
                <li className={v.rankOk ? "up" : "down"}>{v.rankOk ? "✓" : "✗"} rank {v.rank} of {v.of} (stored {r.rank} of {r.of})</li>
              </ul> : <div className="mute small">Recomputes this decision in your browser from that night's readings: checks their SHA-256, then the score and the rank among all {r.of ?? ""} companies.</div>}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Waterfall({ terms, score, A, color, evid }: { terms: { s: string; z: number; w: number; term: number; raw: number | null }[]; score: number; A: Model["A"]; color: string; evid: NonNullable<Model["A"]["meta"]["evidence"]> }) {
  const [ref, { w: W }] = useSize<HTMLDivElement>();
  const rows = terms.length + 1, H = rows * 30 + 10;
  let acc = 0;
  const pts = terms.map(t => { const a = acc; acc += t.term; return { ...t, a, b: acc }; });
  const lo = Math.min(0, ...pts.map(x => Math.min(x.a, x.b)), score), hi = Math.max(0, ...pts.map(x => Math.max(x.a, x.b)), score);
  const L = 120, R = 70, X = (v: number) => L + (Math.max(W, 260) - L - R) * ((v - lo) / ((hi - lo) || 1));
  return (
    <div ref={ref} style={{ position: "relative", height: H }}>
      {W > 0 && <svg width={W} height={H}>
        <line x1={X(0)} x2={X(0)} y1={0} y2={H} stroke="rgba(130,160,220,.25)" />
        {pts.map((t, k) => {
          const y = 6 + k * 30, x1 = X(Math.min(t.a, t.b)), x2 = X(Math.max(t.a, t.b)), st = evid[t.s]?.status;
          return <g key={t.s}>
            <text x={L - 8} y={y + 15} textAnchor="end" fill="#c9d4ec" fontSize="12">{sigLabel(A, t.s)}</text>
            <text x={L - 8} y={y + 26} textAnchor="end" fill="#56627d" fontSize="9.5" fontFamily="var(--num)">w {t.w} · z {nf(t.z, 2)}{st ? " · " + st : ""}</text>
            <rect x={x1} y={y + 4} width={Math.max(2, x2 - x1)} height={18} rx={3} fill={t.term >= 0 ? COLOR.up : COLOR.down} opacity=".75" />
            {k > 0 && <line x1={X(t.a)} x2={X(t.a)} y1={y - 8} y2={y + 4} stroke="rgba(255,255,255,.25)" strokeDasharray="2 2" />}
            <text x={Math.max(W, 260) - R + 8} y={y + 17} fill={t.term >= 0 ? COLOR.up : COLOR.down} fontSize="11.5" fontFamily="var(--num)">{t.term >= 0 ? "+" : "−"}{nf(Math.abs(t.term), 3)}</text>
          </g>;
        })}
        {(() => { const y = 6 + terms.length * 30; return <g>
          <text x={L - 8} y={y + 17} textAnchor="end" fill="#fff" fontSize="12" fontWeight="600">Score</text>
          <rect x={X(Math.min(0, score))} y={y + 4} width={Math.max(2, Math.abs(X(score) - X(0)))} height={18} rx={3} fill={color} style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
          <text x={Math.max(W, 260) - R + 8} y={y + 17} fill="#fff" fontSize="12" fontWeight="600" fontFamily="var(--num)">{nf(score, 3)}</text>
        </g>; })()}
      </svg>}
    </div>
  );
}

// ---------- DNA helix: a rotating double helix whose rungs are the genes, sized by weight ----------
function Helix({ M, p }: { M: Model; p: Participant }) {
  const [ref, { w: W, h: H }] = useSize<HTMLDivElement>();
  const cv = useRef<HTMLCanvasElement>(null);
  const [hot, setHot] = useState<string | null>(null);
  const genes = useMemo(() => Object.entries(p.dna!.w), [p]);
  const mx = Math.max(1, ...genes.map(g => g[1]));
  const col = colorOf(p);
  const hits = useRef<{ k: string; x: number; y: number }[]>([]);
  useEffect(() => {
    const c = cv.current; if (!c || !W || !H) return;
    const dpr = Math.min(devicePixelRatio || 1, 2); c.width = W * dpr; c.height = H * dpr;
    const g = c.getContext("2d")!; g.scale(dpr, dpr);
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0; const t0 = performance.now();
    const draw = () => {
      const t = reduce ? 0 : (performance.now() - t0) / 1000;
      g.clearRect(0, 0, W, H);
      const n = genes.length, top = 18, bot = H - 14, amp = Math.min(W * .22, 70), cx = W / 2;
      const list: { k: string; x: number; y: number; z: number; w: number }[] = [];
      for (let s = 0; s < 2; s++) { // strands
        g.beginPath();
        for (let y = top; y <= bot; y += 3) {
          const ph = (y - top) / (bot - top) * Math.PI * 2.4 + t * 0.8 + s * Math.PI;
          const x = cx + Math.sin(ph) * amp; y === top ? g.moveTo(x, y) : g.lineTo(x, y);
        }
        g.strokeStyle = s ? "rgba(140,170,230,.35)" : col; g.lineWidth = 2; g.shadowColor = col; g.shadowBlur = s ? 0 : 8; g.stroke(); g.shadowBlur = 0;
      }
      genes.forEach(([k, wt], j) => {
        const y = top + (j + .5) / n * (bot - top), ph = (y - top) / (bot - top) * Math.PI * 2.4 + t * 0.8;
        const x1 = cx + Math.sin(ph) * amp, x2 = cx + Math.sin(ph + Math.PI) * amp, depth = Math.cos(ph);
        const a = wt ? .35 + .65 * (wt / mx) : .12;
        g.strokeStyle = wt ? col : "rgba(120,140,180,.4)"; g.globalAlpha = a * (0.55 + 0.45 * (depth + 1) / 2);
        g.lineWidth = wt ? 2 + 6 * wt / mx : 1; g.beginPath(); g.moveTo(x1, y); g.lineTo(x2, y); g.stroke(); g.globalAlpha = 1;
        list.push({ k, x: cx, y, z: depth, w: wt });
        if (wt) { g.fillStyle = "#e7eefc"; g.font = "500 10.5px 'Geist Variable', system-ui"; g.textAlign = "left"; g.globalAlpha = .9; g.fillText(`${sigLabel(M.A, k)} ${wt}`, Math.min(W - 90, cx + amp + 10), y + 3.5); g.globalAlpha = 1; }
      });
      hits.current = list;
      if (!reduce) raf = requestAnimationFrame(draw);
    };
    draw(); return () => cancelAnimationFrame(raf);
  }, [W, H, col, genes, mx, M.A]);
  const onMove = (e: React.PointerEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect(), y = e.clientY - r.top;
    const near = hits.current.reduce((b, h) => Math.abs(h.y - y) < Math.abs((b?.y ?? 1e9) - y) ? h : b, null as null | { k: string; y: number });
    setHot(near && Math.abs(near.y - y) < 12 ? near.k : null);
  };
  const ev = hot ? M.A.meta.evidence?.[hot] : null;
  return (
    <div className="fill" ref={ref} onPointerMove={onMove} onPointerLeave={() => setHot(null)}>
      <canvas ref={cv} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
      {hot && <div className="genetip">
        <b>{sigLabel(M.A, hot)}</b> · weight <span className="num">{p.dna!.w[hot]}</span>
        <br /><span className="mute">evidence: {ev?.status || "not yet measured"}{ev?.obs ? ` · ${ev.obs} obs` : ""}{ev?.t != null ? ` · t ${nf(ev.t, 1)}` : ""}</span>
      </div>}
    </div>
  );
}

function Chart({ M, p, at, decisions, onWhy }: { M: Model; p: Participant; at: number; decisions: Decision[]; onWhy: (d: Decision) => void }) {
  const [ref, { w: W, h: H }] = useSize<HTMLDivElement>();
  const dates = M.A.meta.dates, o = Math.max(0, dates.indexOf(p.from));
  const base = p.s[0] || 1, mine = p.s.map(v => v / base - 1);
  const ix = M.index && p.type !== "index" ? M.index.s.slice(o).map((v, _i, a) => v / a[0] - 1) : [];
  const cap = M.A.meta.capital;
  const band = M.A.luck?.s ? M.A.luck.s.slice(o) : (M.A.band || []).slice(o).map(b => b && [b[0] / cap - 1, b[1] / cap - 1] as [number, number]);
  const m = { l: 46, r: 8, t: 8, b: 30 };
  if (!(W > 0 && H > 0)) return <div className="fill" ref={ref} />;
  const all = [0, ...mine, ...ix, ...band.flat().filter((v): v is number => v != null)];
  let lo = Math.min(...all), hi = Math.max(...all); if (hi - lo < .01) { hi += .005; lo -= .005; }
  const pad = (hi - lo) * .08; lo -= pad; hi += pad;
  const n = Math.max(mine.length, 2);
  const X = (i: number) => m.l + (W - m.l - m.r) * (i / (n - 1)), Y = (v: number) => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
  const line = (a: number[]) => a.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const bf = band.map((b, i) => b ? [i, b] as const : null).filter(Boolean) as (readonly [number, [number, number]])[];
  let peak = -Infinity; const dd = mine.map(v => { peak = Math.max(peak, v); return peak; });
  const col = colorOf(p), ai = at - o;
  const nodes = decisions.filter(d => !d.next && (d.k === "buy" || d.k === "sell")).map(d => ({ d, i: dates.indexOf(d.d) - o })).filter(x => x.i >= 0);
  return (
    <div className="fill" ref={ref}>
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
        {ai >= 0 && ai < n && ai !== n - 1 && <line x1={X(ai)} x2={X(ai)} y1={m.t} y2={H - m.b} stroke="#fff" strokeOpacity=".5" strokeDasharray="3 3" />}
        {/* decision timeline: one node per trade; tap for Why? */}
        <line x1={m.l} x2={W - m.r} y1={H - 12} y2={H - 12} stroke="rgba(130,160,220,.15)" />
        {nodes.map(({ d, i }, k) => <circle key={k} cx={X(i)} cy={H - 12} r={4} fill={d.k === "buy" ? COLOR.up : COLOR.down} opacity=".85" style={{ cursor: d.r ? "pointer" : "default" }}
          onClick={() => d.r && onWhy(d)}><title>{`${d.k} ${tick(d.t)} · ${day(d.d)}`}</title></circle>)}
        {[0, n - 1].map(i => dates[o + i] && <text key={i} x={X(i)} y={H - 18} textAnchor={i ? "end" : "start"} fill="#56627d" fontSize="10.5">{day(dates[o + i])}</text>)}
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
