// X5 lenses fed by the Signal Lab and the intelligence layer: LAB (truth meter) and PEOPLE (disclosures).
// Data files are loaded on demand from data/lab and data/intel; if a file is missing the lens says so.
import { useEffect, useMemo, useState } from "react";
import { COLOR, colorOf, day, nf, pct, sigLabel, type Model } from "./data";
import { Shape } from "./hud";

const cache = new Map<string, Promise<unknown>>();
export function loadData<T>(path: string): Promise<T | null> {
  if (!cache.has(path)) cache.set(path, fetch("./data/" + path).then(r => r.ok ? r.json() : null).catch(() => null));
  return cache.get(path) as Promise<T | null>;
}
export function useData<T>(path: string) {
  const [v, setV] = useState<T | null | undefined>(undefined);
  useEffect(() => { let on = true; loadData<T>(path).then(x => on && setV(x)); return () => { on = false; }; }, [path]);
  return v;   // undefined = loading, null = not available
}

// ---------------- LAB ----------------
type Gates = Record<string, boolean>;
type Official = { signals: Record<string, { status: string; family?: string; horizon_days?: number; observations: number; mean_ic: number | null; nw_t: number | null; subperiod_mean_ic: number[]; gates: Gates }>; gates: { min_nw_t: number; min_observations: number; subperiods: number }; note?: string };
type Prov = { generated_at: string; signals: Record<string, { family: string; expected_sign: number; horizon_days: number; live: { n_days: number; status: string }; rehearsal?: { n_days: number; first: string; last: string; mean_ic_expected_direction: number; newey_west_t: number; subperiod_mean_ic_expected_direction: number[]; hit_rate: number; gates: Gates; status: string } }> };
type Card = { id: string; name: string; family: string; status: string; ic: number | null; t: number | null; obs: number; subs: number[]; gates: Gates; kind: "live" | "rehearsal"; note?: string };

const LADDER = ["shadow", "candidate", "admitted", "rejected"] as const;
const pretty = (x: string) => x.includes("_") ? (x.charAt(0).toUpperCase() + x.slice(1)).replace(/_/g, " ").replace(/ (\d+)([dmw])$/, " $1$2") : x;
const stage = (s: string) => s === "passes_gates" ? "candidate" : s === "admitted" ? "admitted" : s === "rejected" ? "rejected" : "shadow";

export function Lab({ M, onPick }: { M: Model; onPick: (id: string) => void }) {
  const off = useData<Official>("lab/report.json"), prov = useData<Prov>("lab/ic_provisional.json");
  const cards = useMemo(() => {
    const out: Card[] = [];
    Object.entries(off?.signals || {}).forEach(([k, v]) => out.push({ id: k, name: pretty(sigLabel(M.A, k.split(".").pop()!)), family: v.family || "price", status: v.status, ic: v.mean_ic, t: v.nw_t, obs: v.observations, subs: v.subperiod_mean_ic || [], gates: v.gates || {}, kind: "live" }));
    Object.entries(prov?.signals || {}).forEach(([k, v]) => {
      const r = v.rehearsal;
      out.push({ id: k, name: pretty(k.split(".").pop()!), family: v.family, status: r?.status || "shadow", ic: r?.mean_ic_expected_direction ?? null, t: r?.newey_west_t ?? null, obs: r?.n_days || 0, subs: r?.subperiod_mean_ic_expected_direction || [], gates: r?.gates || {}, kind: "rehearsal", note: `live: ${v.live.status}` });
    });
    return out;
  }, [off, prov, M.A]);
  const tMax = Math.max(4, ...cards.map(c => Math.abs(c.t || 0)));
  const need = off?.gates?.min_nw_t ?? 3;
  const ranked = M.agents.slice().sort((a, b) => (b.pctAll ?? -1) - (a.pctAll ?? -1));
  return (
    <section className="lab">
      <div className="lab-ladder glass">
        <header><span className="lbl">Evidence ladder · a signal earns its place, never assumed</span><span className="lbl faint">admission needs t &gt; {need} over ≥{off?.gates?.min_observations ?? 250} days, stable in {off?.gates?.subperiods ?? 3} sub-periods, net of costs</span></header>
        {off === undefined || prov === undefined ? <div className="empty">Loading…</div> : !cards.length ? <div className="empty">No Signal Lab report yet.</div> :
          <div className="ladder">
            {LADDER.map(st => (
              <div key={st} className={"rung " + st}>
                <div className="lbl">{st}</div>
                {cards.filter(c => stage(c.status) === st).map(c => (
                  <div key={c.id} className="sig" title={c.note || ""}>
                    <div className="sig-h"><b>{c.name}</b><span className={"badge " + (c.kind === "rehearsal" ? "reh" : "")}>{c.kind === "rehearsal" ? "rehearsal (backfilled data)" : "live"}</span></div>
                    <div className="mute small">{c.family} · {nf(c.obs)} days</div>
                    <div className="tgauge" title={`Newey–West t ${nf(c.t, 2)} (needs > ${need})`}>
                      <i className="need" style={{ left: `${need / tMax * 50 + 50}%` }} />
                      {c.t != null && <i className="val" style={{ [c.t >= 0 ? "left" : "right"]: "50%", width: `${Math.min(50, Math.abs(c.t) / tMax * 50)}%`, background: Math.abs(c.t) >= need ? COLOR.up : COLOR.luck } as React.CSSProperties} />}
                    </div>
                    <div className="sig-f num"><span>IC {c.ic == null ? "—" : nf(c.ic, 3)}</span><span>t {c.t == null ? "—" : nf(c.t, 2)}</span>
                      <span className="subs">{c.subs.map((x, k) => <i key={k} style={{ height: Math.min(14, 3 + Math.abs(x) * 200), background: x >= 0 ? COLOR.up : COLOR.down }} />)}</span></div>
                    <div className="gates">{Object.entries(c.gates).map(([g, ok]) => <span key={g} className={ok ? "up" : "faint"} title={g.replace(/_/g, " ")}>{ok ? "✓" : "·"}</span>)}</div>
                  </div>
                ))}
              </div>
            ))}
          </div>}
        <div className="evo-note">"Rehearsal" = the signal replayed on past data before it was registered; it never counts as evidence. "Live" = measured only on days after registration. {off?.note}</div>
      </div>
      <div className="lab-luck glass">
        <header><span className="lbl">Luck-o-meter · each agent vs {nf(M.luckN)} random monkeys</span></header>
        <div className="luckrows">
          {ranked.map(p => (
            <button key={p.id} className="jrow" onClick={() => onPick(p.id)}>
              <span><Shape p={p} /> {p.name}</span>
              <span className="lm"><i style={{ width: `${(p.pctAll ?? 0) * 100}%`, background: colorOf(p) }} /><b style={{ left: "95%" }} /></span>
              <span className="num">{p.pctAll == null ? "—" : nf(p.pctAll * 100) + "%"}</span>
            </button>
          ))}
        </div>
        <div className="evo-note">The white tick is the 95% line: only an agent beyond it, for long enough, earns the merit badge. Deflated Sharpe arrives in phase 3.</div>
      </div>
    </section>
  );
}

// ---------------- PEOPLE ----------------
type Alert = { kind: "insider" | "congress"; person_name: string; role?: string; ticker: string; action: "buy" | "sell"; size_low?: number; size_high?: number; traded_on?: string; disclosed_at?: string; delay_days?: number; note?: string; source_id?: string };
type Mirror = { rule: string; note: string; by_kind: Record<string, { trades: number; closed: number; mean_excess_closed: number; hit_rate_closed: number }> };

export function People({ M }: { M: Model }) {
  const A = useData<{ wording: string; alerts: Alert[]; generated_at: string }>("intel/alerts.json");
  const mirror = useData<Mirror>("lab/mirror_book.json");
  const [kind, setKind] = useState<"all" | "insider" | "congress">("all");
  const [hot, setHot] = useState<string | null>(null);
  const list = (A?.alerts || []).filter(a => kind === "all" || a.kind === kind);
  const tickers = [...new Set(list.map(a => a.ticker))].slice(0, 14);
  const W = 520, H = 440, cx = W / 2, cy = H / 2;
  const tpos = (k: number) => { const a = k / Math.max(1, tickers.length) * Math.PI * 2 - Math.PI / 2; return [cx + Math.cos(a) * 120, cy + Math.sin(a) * 120] as const; };
  const held = new Set(M.agents.flatMap(p => p.hold.map(h => h.t)));
  return (
    <section className="people">
      <div className="ppl-orbit glass">
        <header><span className="lbl">People around their companies</span>
          <nav className="seg">{(["all", "insider", "congress"] as const).map(k => <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{k.toUpperCase()}</button>)}</nav></header>
        {A === undefined ? <div className="empty">Loading…</div> : !A ? <div className="empty big-empty">No disclosures yet.</div> :
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
            <circle cx={cx} cy={cy} r={120} fill="none" stroke="rgba(130,160,220,.12)" />
            {tickers.map((t, k) => {
              const [x, y] = tpos(k), ppl = list.filter(a => a.ticker === t);
              return <g key={t} onPointerEnter={() => setHot(t)} onPointerLeave={() => setHot(null)} opacity={hot && hot !== t ? .35 : 1}>
                {ppl.slice(0, 8).map((a, j) => {
                  const ang = j / Math.min(8, ppl.length) * Math.PI * 2, r = 30 + (j % 2) * 10;
                  const px = x + Math.cos(ang) * r, py = y + Math.sin(ang) * r, col = a.action === "buy" ? COLOR.up : COLOR.down;
                  return <g key={j}><line x1={x} y1={y} x2={px} y2={py} stroke={col} strokeOpacity=".35" />
                    <circle cx={px} cy={py} r={a.kind === "congress" ? 5 : 3.5} fill={a.kind === "congress" ? "none" : col} stroke={col} strokeWidth="1.5"><title>{`${a.person_name} · ${a.action} · delay ${a.delay_days}d`}</title></circle></g>;
                })}
                <circle cx={x} cy={y} r={16} fill={held.has(t) ? "rgba(56,198,255,.25)" : "rgba(255,255,255,.06)"} stroke={held.has(t) ? COLOR.index : "rgba(255,255,255,.25)"} />
                <text x={x} y={y + 4} textAnchor="middle" fill="#e7eefc" fontSize="10" fontWeight="600">{t}</text>
              </g>;
            })}
            <text x={cx} y={cy - 4} textAnchor="middle" fill="#8b98b5" fontSize="11" letterSpacing="2">DISCLOSURES</text>
            <text x={cx} y={cy + 12} textAnchor="middle" fill="#56627d" fontSize="10">● insider  ○ Congress · blue ring = held by an agent</text>
          </svg>}
        {A && <div className="evo-note">{A.wording} Filled dots: insiders (SEC filings). Rings: members of Congress (non-commercial use only).</div>}
      </div>
      <div className="ppl-list glass">
        <header><span className="lbl">Latest disclosures · delay always shown</span><span className="lbl faint">{A?.generated_at ? day(A.generated_at.slice(0, 10)) : ""}</span></header>
        <div className="plist">
          {list.slice(0, 40).map((a, k) => (
            <div key={k} className={"prow" + (hot && hot !== a.ticker ? " dim" : "")} onPointerEnter={() => setHot(a.ticker)} onPointerLeave={() => setHot(null)}>
              <span className={"k-" + (a.action === "buy" ? "buy" : "sell")}>{a.action}</span>
              <b>{a.ticker}</b>
              <span className="pname">{a.person_name}<small className="mute"> · {a.kind === "congress" ? "Congress" : a.role || "insider"}</small></span>
              <span className="num mute">{a.size_low != null ? (a.size_low === a.size_high ? "$" + nf(a.size_low) : `$${nf(a.size_low)}–${nf(a.size_high)}`) : ""}</span>
              <span className="badge" title={`traded ${a.traded_on}, disclosed ${a.disclosed_at?.slice(0, 10)}`}>+{nf(a.delay_days)}d</span>
            </div>
          ))}
        </div>
        {mirror && <div className="mirror">
          <div className="lbl">Mirror · shadow book (never trades)</div>
          <div className="row3">{Object.entries(mirror.by_kind).map(([k, v]) => <div key={k}><div className="lbl">{k}</div>
            <div className={"num " + (v.mean_excess_closed >= 0 ? "up" : "down")}>{pct(v.mean_excess_closed, 1)}</div>
            <div className="faint small num">{v.closed} closed · hit {pct(v.hit_rate_closed, 0, false)}</div></div>)}</div>
          <div className="faint small">{mirror.rule}. {mirror.note}</div>
        </div>}
      </div>
    </section>
  );
}
