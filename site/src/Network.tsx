// NETWORK lens: the knowledge graph (companies, sectors, people, insiders, members of Congress, countries)
// with a time slider ("as known at T": only links whose start date is on or before T). Tap a node to light
// up everything connected to it. Loaded on demand.
import { useEffect, useMemo, useRef, useState } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from "d3-force";
import { COLOR, day } from "./data";
import { useData } from "./Intel";

type GNode = { id: string; type: string; label: string; name?: string; sector?: string };
type GEdge = { a: string; b: string; kind: string; since?: string; count?: number; value_usd?: number };
type Graph = { as_of: string; window_days: number; nodes: GNode[]; edges: GEdge[] };
type N = GNode & SimulationNodeDatum & { deg: number };

const TYPE_COLOR: Record<string, string> = {
  company: "#38c6ff", sector: "#ffd34d", person: "#b07cff", insider: "#8b98b5", member_of_congress: "#ff5fa2", country: "#2fe0a8", institution: "#ff8a3d",
};
const KIND_COLOR: Record<string, string> = {
  in_sector: "rgba(255,211,77,.25)", ceo: "rgba(176,124,255,.5)", chairperson: "rgba(176,124,255,.5)", head_of_state: "rgba(47,224,168,.45)", head_of_government: "rgba(47,224,168,.45)",
  insider_buy: "rgba(62,224,143,.55)", insider_sell: "rgba(255,107,107,.45)", congress_buy: "rgba(62,224,143,.55)", congress_sell: "rgba(255,107,107,.45)",
};
const TYPES = ["company", "sector", "person", "insider", "member_of_congress", "country"] as const;
const TYPE_LABEL: Record<string, string> = { company: "Companies", sector: "Sectors", person: "Executives", insider: "Insiders", member_of_congress: "Congress", country: "Countries", institution: "Institutions" };

export default function Network() {
  const G = useData<Graph>("intel/graph.json");
  const box = useRef<HTMLDivElement>(null), cv = useRef<HTMLCanvasElement>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [hidden, setHidden] = useState<Set<string>>(new Set(["insider"]));
  const dates = useMemo(() => [...new Set((G?.edges || []).map(e => e.since).filter(Boolean) as string[])].sort(), [G]);
  const [ti, setTi] = useState<number | null>(null);
  const T = ti == null ? dates[dates.length - 1] : dates[ti];
  const view = useRef({ k: 1, x: 0, y: 0, drag: null as null | { x: number; y: number; vx: number; vy: number } });

  const { nodes, edges } = useMemo(() => {
    if (!G) return { nodes: [] as N[], edges: [] as (GEdge & { s: N; t: N })[] };
    const keep = G.edges.filter(e => !T || !e.since || e.since <= T);
    const deg = new Map<string, number>(); keep.forEach(e => { deg.set(e.a, (deg.get(e.a) || 0) + 1); deg.set(e.b, (deg.get(e.b) || 0) + 1); });
    const ns: N[] = G.nodes.filter(n => !hidden.has(n.type) && (deg.get(n.id) || n.type === "company" || n.type === "sector")).map(n => ({ ...n, deg: deg.get(n.id) || 0 }));
    const by = new Map(ns.map(n => [n.id, n]));
    const es = keep.filter(e => by.has(e.a) && by.has(e.b)).map(e => ({ ...e, s: by.get(e.a)!, t: by.get(e.b)! }));
    const sim = forceSimulation(ns)
      .force("link", forceLink(es.map(e => ({ source: e.s, target: e.t, kind: e.kind }))).distance(l => (l as unknown as { kind: string }).kind === "in_sector" ? 60 : 26).strength(.5))
      .force("charge", forceManyBody().strength(-26).distanceMax(260))
      .force("collide", forceCollide<N>(n => 3 + Math.sqrt(n.deg) * 1.3))
      .force("center", forceCenter(0, 0)).force("x", forceX(0).strength(.03)).force("y", forceY(0).strength(.03))
      .stop();
    for (let k = 0; k < 220; k++) sim.tick();
    return { nodes: ns, edges: es };
  }, [G, T, hidden]);

  const neigh = useMemo(() => {
    if (!sel) return null;
    const s = new Set([sel]); edges.forEach(e => { if (e.a === sel) s.add(e.b); if (e.b === sel) s.add(e.a); });
    return s;
  }, [sel, edges]);

  useEffect(() => {
    const c = cv.current, b = box.current; if (!c || !b) return;
    let raf = 0;
    const draw = () => {
      const w = b.clientWidth, h = b.clientHeight, dpr = Math.min(devicePixelRatio || 1, 2);
      if (c.width !== w * dpr || c.height !== h * dpr) { c.width = w * dpr; c.height = h * dpr; }
      const g = c.getContext("2d")!, v = view.current;
      g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
      g.translate(w / 2 + v.x, h / 2 + v.y); g.scale(v.k, v.k);
      for (const e of edges) {
        const on = !neigh || (neigh.has(e.a) && neigh.has(e.b) && (e.a === sel || e.b === sel));
        g.strokeStyle = on ? (KIND_COLOR[e.kind] || "rgba(150,170,210,.3)") : "rgba(120,140,180,.04)";
        g.lineWidth = (on && neigh ? 1.6 : .7) / v.k;
        g.beginPath(); g.moveTo(e.s.x!, e.s.y!); g.lineTo(e.t.x!, e.t.y!); g.stroke();
      }
      for (const n of nodes) {
        const r = n.type === "sector" ? 7 : n.type === "company" ? 3 + Math.sqrt(n.deg) * .9 : 2.2 + Math.sqrt(n.deg) * .5;
        const on = !neigh || neigh.has(n.id), col = TYPE_COLOR[n.type] || "#9aa4b8";
        g.globalAlpha = on ? 1 : .12; g.fillStyle = col;
        if (n.id === sel) { g.shadowColor = col; g.shadowBlur = 16; }
        g.beginPath(); g.arc(n.x!, n.y!, r, 0, Math.PI * 2); g.fill(); g.shadowBlur = 0;
        if ((n.type === "sector" || n.type === "country" || (neigh && on) || (n.type === "company" && v.k > 1.6)) ) {
          g.fillStyle = "rgba(231,238,252,.85)"; g.font = `${n.type === "sector" ? 600 : 500} ${11 / v.k}px 'Geist Variable', system-ui`;
          g.fillText(n.type === "company" ? n.id.replace(/^co:/, "") : n.label, n.x! + r + 2, n.y! + 3.5 / v.k);
        }
        g.globalAlpha = 1;
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [nodes, edges, neigh, sel]);

  const toWorld = (cx: number, cy: number) => { const b = box.current!.getBoundingClientRect(), v = view.current; return [(cx - b.left - b.width / 2 - v.x) / v.k, (cy - b.top - b.height / 2 - v.y) / v.k]; };
  const pick = (cx: number, cy: number) => { const [x, y] = toWorld(cx, cy); let best: N | null = null, bd = 12 / view.current.k; for (const n of nodes) { const d = Math.hypot(n.x! - x, n.y! - y); if (d < bd) { bd = d; best = n; } } return best; };
  const down = (e: React.PointerEvent) => { const v = view.current; v.drag = { x: e.clientX, y: e.clientY, vx: v.x, vy: v.y }; (e.target as Element).setPointerCapture(e.pointerId); };
  const move = (e: React.PointerEvent) => { const v = view.current; if (v.drag) { v.x = v.drag.vx + e.clientX - v.drag.x; v.y = v.drag.vy + e.clientY - v.drag.y; } };
  const up = (e: React.PointerEvent) => { const v = view.current, d = v.drag; v.drag = null; if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) < 5) { const n = pick(e.clientX, e.clientY); setSel(n ? n.id : null); } };
  const wheel = (e: React.WheelEvent) => { const v = view.current; v.k = Math.max(.4, Math.min(5, v.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15))); };
  const S = sel ? nodes.find(n => n.id === sel) : null;
  const links = S ? edges.filter(e => e.a === S.id || e.b === S.id) : [];
  const search = (s: string) => { setQ(s); const t = s.trim().toLowerCase(); if (!t) return; const n = nodes.find(n => n.label.toLowerCase().includes(t) || n.id.toLowerCase() === "co:" + t); if (n) setSel(n.id); };
  return (
    <section className="network">
      <div className="graph glass">
        <header>
          <span className="lbl">Network · who is linked to whom{T ? ` · as known on ${day(T)}` : ""}</span>
          <input className="gsearch" placeholder="Find a company, person, country…" value={q} onChange={e => search(e.target.value)} />
        </header>
        <div className="gtypes">{TYPES.map(t => <button key={t} className={"chip" + (hidden.has(t) ? "" : " on")} onClick={() => setHidden(h => { const n = new Set(h); n.has(t) ? n.delete(t) : n.add(t); return n; })}>
          <span className="dot" style={{ background: TYPE_COLOR[t] }} />{TYPE_LABEL[t]}</button>)}</div>
        <div className="gbox" ref={box} onPointerDown={down} onPointerMove={move} onPointerUp={up} onWheel={wheel}>
          {G === undefined ? <div className="empty">Loading…</div> : !G ? <div className="empty big-empty">The knowledge graph is not in the archive yet.</div> : <canvas ref={cv} />}
        </div>
        {dates.length > 1 && <div className="gtime"><span className="lbl">Time</span>
          <input type="range" min={0} max={dates.length - 1} value={ti ?? dates.length - 1} onChange={e => setTi(+e.target.value)} />
          <span className="num">{day(T)}</span></div>}
      </div>
      <div className="gside glass">
        {!S ? <>
          <div className="lbl">How to read</div>
          <div className="evo-note">Each dot is a company, sector, executive, insider, member of Congress or country. Lines: sector membership, CEO and chair roles, heads of state and government, and insider or Congress trades over the last {G?.window_days ?? 180} days (green buy, red sell). Tap a dot to light up its links; drag to move, scroll to zoom. Slide the time bar to see the network as it was known on a day.</div>
          <div className="lbl">Busiest nodes</div>
          {nodes.slice().sort((a, b) => b.deg - a.deg).slice(0, 12).map(n => <button key={n.id} className="jrow" onClick={() => setSel(n.id)}><span><span className="dot" style={{ background: TYPE_COLOR[n.type] }} /> {n.label}</span><span /><span className="num mute">{n.deg}</span></button>)}
        </> : <>
          <div className="gsel"><span className="dot" style={{ background: TYPE_COLOR[S.type] }} /><b>{S.label}</b><span className="mute small">{TYPE_LABEL[S.type] || S.type}</span><button className="round" style={{ marginLeft: "auto" }} onClick={() => setSel(null)} aria-label="Clear">✕</button></div>
          <div className="lbl">{links.length} links</div>
          <div className="glinks">{links.slice(0, 60).map((e, k) => {
            const o = e.a === S.id ? e.t : e.s;
            return <button key={k} className="jrow" onClick={() => setSel(o.id)}>
              <span><span className="dot" style={{ background: TYPE_COLOR[o.type] }} /> {o.label}</span>
              <span className="mute small" style={{ color: /buy/.test(e.kind) ? COLOR.up : /sell/.test(e.kind) ? COLOR.down : undefined }}>{e.kind.replace(/_/g, " ")}{e.count ? ` ×${e.count}` : ""}</span>
              <span className="num faint small">{e.since ? day(e.since) : ""}</span></button>;
          })}</div>
        </>}
        <div className="evo-note">Sources: SEC filings (insiders), Congress disclosures (non-commercial use), Wikidata (roles, heads of state). As of {G?.as_of?.slice(0, 10) || "—"}.</div>
      </div>
    </section>
  );
}
