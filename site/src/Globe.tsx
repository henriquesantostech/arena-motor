// WORLD lens: a rotating Earth (orthographic, drawn on canvas) with each country's events of the day
// (GDELT), the central-bank rates, currencies and risk gauges. Loaded on demand with its map data.
import { useEffect, useMemo, useRef, useState } from "react";
import { feature } from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";
import land110 from "world-atlas/land-110m.json";
import { COLOR, day, nf } from "./data";
import { useData } from "./Intel";

type Country = { name: string; lat: number; lon: number; events: number; conflict_share: number; goldstein: number; tone: number; day: string; head_of_state?: string[]; head_of_government?: string[] };
type V = { value: number; day: string };
type World = { as_of: string; countries: Record<string, Country>; rates: Record<string, V>; fx_per_eur: Record<string, V>; risk: Record<string, V>; events: { doc_id: string; title: string; day: string; topic: string }[] };
type Docs = { docs: Record<string, { title?: string; url?: string; source?: string }> };

const RATE_LABEL: Record<string, string> = { ust_3m: "US 3M", ust_2y: "US 2Y", ust_10y: "US 10Y", ust_30y: "US 30Y", estr: "€STR", euribor_3m: "Euribor 3M", fed_funds: "Fed funds" };
const rings: [number, number][][] = (() => {
  const f = feature(land110 as unknown as Topology, (land110 as unknown as Topology).objects.land as GeometryCollection) as unknown as { features: { geometry: { type: string; coordinates: number[][][] | number[][][][] } }[] };
  const out: [number, number][][] = [];
  for (const ft of f.features) {
    const g = ft.geometry;
    const polys = g.type === "Polygon" ? [g.coordinates as number[][][]] : (g.coordinates as number[][][][]);
    for (const p of polys) out.push(p[0] as [number, number][]);
  }
  return out;
})();

export default function Globe() {
  const W = useData<World>("intel/world.json"), docs = useData<Docs>("intel/docs.json");
  const cv = useRef<HTMLCanvasElement>(null), box = useRef<HTMLDivElement>(null);
  const [sel, setSel] = useState<string | null>(null);
  const rot = useRef({ lon: -20, lat: 18, drag: null as null | { x: number; y: number; lon: number; lat: number }, auto: true });
  const pts = useRef<{ k: string; x: number; y: number; r: number }[]>([]);
  const list = useMemo(() => Object.entries(W?.countries || {}).sort((a, b) => b[1].events - a[1].events), [W]);
  const maxE = Math.max(1, ...list.map(([, c]) => c.events));

  useEffect(() => {
    const c = cv.current, b = box.current; if (!c || !b || !W) return;
    const g = c.getContext("2d")!; const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0, last = performance.now();
    const draw = (now: number) => {
      const dt = Math.min(.05, (now - last) / 1000); last = now;
      const w = b.clientWidth, h = b.clientHeight, dpr = Math.min(devicePixelRatio || 1, 2);
      if (c.width !== w * dpr || c.height !== h * dpr) { c.width = w * dpr; c.height = h * dpr; }
      g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
      const R = Math.min(w, h) * .42, cx = w / 2, cy = h / 2, r = rot.current;
      if (r.auto && !reduce && !r.drag) r.lon += dt * 6;
      const l0 = r.lon * Math.PI / 180, p0 = r.lat * Math.PI / 180, sp0 = Math.sin(p0), cp0 = Math.cos(p0);
      const proj = (lon: number, lat: number) => {
        const l = lon * Math.PI / 180 - l0, p = lat * Math.PI / 180, cp = Math.cos(p);
        const cosc = sp0 * Math.sin(p) + cp0 * cp * Math.cos(l);
        return { x: cx + R * cp * Math.sin(l), y: cy - R * (cp0 * Math.sin(p) - sp0 * cp * Math.cos(l)), v: cosc > 0 };
      };
      // atmosphere + ocean
      const atm = g.createRadialGradient(cx, cy, R * .9, cx, cy, R * 1.25);
      atm.addColorStop(0, "rgba(56,198,255,.25)"); atm.addColorStop(1, "rgba(56,198,255,0)");
      g.fillStyle = atm; g.beginPath(); g.arc(cx, cy, R * 1.25, 0, Math.PI * 2); g.fill();
      const sea = g.createRadialGradient(cx - R * .35, cy - R * .35, R * .1, cx, cy, R);
      sea.addColorStop(0, "#123056"); sea.addColorStop(1, "#050d1f");
      g.fillStyle = sea; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fill();
      // graticule
      g.strokeStyle = "rgba(120,170,255,.10)"; g.lineWidth = 1;
      for (let lon = -180; lon < 180; lon += 30) { g.beginPath(); let on = false; for (let lat = -90; lat <= 90; lat += 3) { const q = proj(lon, lat); if (q.v) { on ? g.lineTo(q.x, q.y) : g.moveTo(q.x, q.y); on = true; } else on = false; } g.stroke(); }
      for (let lat = -60; lat <= 60; lat += 30) { g.beginPath(); let on = false; for (let lon = -180; lon <= 180; lon += 3) { const q = proj(lon, lat); if (q.v) { on ? g.lineTo(q.x, q.y) : g.moveTo(q.x, q.y); on = true; } else on = false; } g.stroke(); }
      // land: hidden points pushed to the horizon so polygons stay closed
      g.fillStyle = "rgba(120,160,220,.16)"; g.strokeStyle = "rgba(150,200,255,.35)";
      for (const ring of rings) {
        let any = false; g.beginPath();
        ring.forEach(([lon, lat], k) => {
          const q = proj(lon, lat); let x = q.x, y = q.y;
          if (!q.v) { const d = Math.hypot(x - cx, y - cy) || 1; x = cx + (x - cx) / d * R; y = cy + (y - cy) / d * R; } else any = true;
          k ? g.lineTo(x, y) : g.moveTo(x, y);
        });
        if (any) { g.closePath(); g.fill(); g.stroke(); }
      }
      // countries: pulse size = events, colour = share of material conflict
      const out: typeof pts.current = [];
      for (const [k, c0] of list) {
        const q = proj(c0.lon, c0.lat); if (!q.v) continue;
        const rr = 3 + Math.sqrt(c0.events / maxE) * 18, conflict = Math.min(1, c0.conflict_share * 3);
        const col = `rgba(${Math.round(80 + 175 * conflict)},${Math.round(200 - 120 * conflict)},${Math.round(255 - 160 * conflict)},`;
        const pulse = reduce ? 0 : (Math.sin(now / 600 + c0.lon) + 1) / 2;
        g.fillStyle = col + (.3 + .15 * pulse) + ")"; g.beginPath(); g.arc(q.x, q.y, rr * (1 + .25 * pulse), 0, Math.PI * 2); g.fill();
        g.fillStyle = col + ".95)"; g.beginPath(); g.arc(q.x, q.y, 2.5, 0, Math.PI * 2); g.fill();
        if (k === sel) { g.strokeStyle = "#fff"; g.lineWidth = 2; g.beginPath(); g.arc(q.x, q.y, rr + 4, 0, Math.PI * 2); g.stroke(); g.lineWidth = 1; }
        if (rr > 9 || k === sel) { g.fillStyle = "rgba(231,238,252,.85)"; g.font = "600 11px 'Geist Variable', system-ui"; g.fillText(k, q.x + rr + 3, q.y + 4); }
        out.push({ k, x: q.x, y: q.y, r: Math.max(rr, 8) });
      }
      pts.current = out;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [W, list, maxE, sel]);

  const down = (e: React.PointerEvent) => { const r = rot.current; r.drag = { x: e.clientX, y: e.clientY, lon: r.lon, lat: r.lat }; r.auto = false; (e.target as Element).setPointerCapture(e.pointerId); };
  const move = (e: React.PointerEvent) => { const r = rot.current; if (!r.drag) return; r.lon = r.drag.lon - (e.clientX - r.drag.x) * .35; r.lat = Math.max(-70, Math.min(70, r.drag.lat + (e.clientY - r.drag.y) * .35)); };
  const up = (e: React.PointerEvent) => {
    const r = rot.current, d = r.drag; r.drag = null;
    if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) < 5) {
      const b = box.current!.getBoundingClientRect(), x = e.clientX - b.left, y = e.clientY - b.top;
      const hit = pts.current.find(p => Math.hypot(p.x - x, p.y - y) < p.r); setSel(hit ? hit.k : null);
    }
  };
  const C = sel ? W?.countries[sel] : null;
  const rates = Object.entries(W?.rates || {});
  return (
    <section className="world">
      <div className="globe glass">
        <header><span className="lbl">World · events of the day by country</span><span className="lbl faint">{W ? "as of " + W.as_of.slice(0, 16).replace("T", " ") + " UTC" : ""}</span></header>
        <div className="gbox" ref={box} onPointerDown={down} onPointerMove={move} onPointerUp={up}>
          {W === undefined ? <div className="empty">Loading…</div> : !W ? <div className="empty big-empty">The world layer is not in the archive yet.</div> : <canvas ref={cv} />}
          {C && <div className="ctip glass">
            <b>{C.name}</b> <span className="faint num">{day(C.day)}</span>
            <div className="row3 small"><div><div className="lbl">Events</div><div className="num">{nf(C.events)}</div></div>
              <div title="Share of events that are material conflict"><div className="lbl">Conflict</div><div className={"num " + (C.conflict_share > .15 ? "down" : "")}>{nf(C.conflict_share * 100, 1)}%</div></div>
              <div title="Average Goldstein scale, −10 (conflict) to +10 (cooperation)"><div className="lbl">Goldstein</div><div className={"num " + (C.goldstein < 0 ? "down" : "up")}>{nf(C.goldstein, 2)}</div></div></div>
            {(C.head_of_state?.length || C.head_of_government?.length) ? <div className="small mute">Head of state: {C.head_of_state?.join(", ") || "—"} · Government: {C.head_of_government?.join(", ") || "—"}</div> : null}
          </div>}
        </div>
        <div className="evo-note">Dot size = number of events; colour from blue to red = share of material conflict. Drag to turn, tap a country. Sources: <a href="https://www.gdeltproject.org/" target="_blank" rel="noreferrer noopener">GDELT Project</a>; map: Natural Earth.</div>
      </div>
      <div className="wside glass">
        <div className="lbl">Rates (%)</div>
        <div className="rates">{rates.map(([k, v]) => <div key={k} title={"as of " + v.day}><span className="mute">{RATE_LABEL[k] || k}</span><b className="num">{nf(v.value, 2)}</b></div>)}</div>
        <div className="lbl">Currencies per €</div>
        <div className="rates">{Object.entries(W?.fx_per_eur || {}).map(([k, v]) => <div key={k} title={"as of " + v.day}><span className="mute">{k}</span><b className="num">{nf(v.value, k === "JPY" ? 2 : 4)}</b></div>)}</div>
        <div className="lbl">Risk gauges</div>
        <div className="rates">
          {W?.risk?.gpr && <div title={"as of " + W.risk.gpr.day}><span className="mute">Geopolitical risk <a href="https://www.matteoiacoviello.com/gpr.htm" target="_blank" rel="noreferrer noopener">(Caldara–Iacoviello)</a></span><b className="num">{nf(W.risk.gpr.value, 0)}</b></div>}
          {W?.risk?.epu && <div title={"as of " + W.risk.epu.day}><span className="mute">Policy uncertainty <a href="https://www.policyuncertainty.com/" target="_blank" rel="noreferrer noopener">(Baker–Bloom–Davis)</a></span><b className="num">{nf(W.risk.epu.value, 0)}</b></div>}
        </div>
        <div className="lbl">Notable events</div>
        <div className="wevents">{(W?.events || []).slice(0, 14).map(e => {
          const d = docs?.docs?.[e.doc_id];
          return <div key={e.doc_id} className="wev"><span className="faint num">{day(e.day)}</span><span className="topic" style={{ color: COLOR.index }}>{e.topic}</span>
            {d?.url ? <a href={d.url} target="_blank" rel="noreferrer noopener">{e.title}</a> : <span>{e.title}</span>}</div>;
        })}</div>
      </div>
    </section>
  );
}
