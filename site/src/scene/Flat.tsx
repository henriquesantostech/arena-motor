// Lite tier: the same reading as the 3D world, seen from the side, in SVG.
import { useEffect, useRef, useState } from "react";
import { COLOR, colorOf, pct, type Model } from "../data";

export function Flat({ M, onPick, onHover, onReady }: { M: Model; onPick: (id: string) => void; onHover: (id: string | null, x?: number, y?: number) => void; onReady: (w: "2d") => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [s, setS] = useState({ w: innerWidth, h: innerHeight });
  useEffect(() => {
    const el = ref.current!; const ro = new ResizeObserver(() => setS({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el); onReady("2d"); return () => ro.disconnect();
  }, [onReady]);
  const { w: W, h: H } = s, phone = W < 820;
  const m = phone ? { l: 16, r: 16, t: 150, b: 210 } : { l: 310, r: 320, t: 110, b: 230 };
  const pw = Math.max(50, W - m.l - m.r), ph = Math.max(50, H - m.t - m.b), y0 = m.t + ph / 2;
  const P = M.A.p;
  const span = Math.max(.04, ...P.map(p => Math.abs(M.gap(p))), ...(M.luck ? M.luck.map(Math.abs) : []));
  const y = (g: number) => y0 - Math.max(-1, Math.min(1, g / span)) * (ph / 2 - 16);
  const cols = [...M.species, "monkey", "equal"], cw = pw / cols.length;
  return (
    <div ref={ref} style={{ position: "absolute", inset: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" onPointerLeave={() => onHover(null)}>
        <defs><linearGradient id="wg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={COLOR.index} stopOpacity=".22" /><stop offset="1" stopColor={COLOR.index} stopOpacity="0" /></linearGradient></defs>
        <rect x={m.l} y={y0} width={pw} height={ph / 2} fill="url(#wg)" />
        {M.luck && <>
          <rect x={m.l} y={y(M.luck[1])} width={pw} height={Math.max(1, y(M.luck[0]) - y(M.luck[1]))} fill={COLOR.luck} opacity=".08" />
          <line x1={m.l} x2={m.l + pw} y1={y(M.luck[1])} y2={y(M.luck[1])} stroke="#c8cfdc" strokeOpacity=".35" strokeDasharray="3 4" />
          <text x={m.l + pw - 4} y={y(M.luck[1]) - 6} textAnchor="end" fill="#8b98b5" fontSize="11">luck band</text>
        </>}
        <line x1={m.l} x2={m.l + pw} y1={y0} y2={y0} stroke={COLOR.index} strokeWidth="2" />
        <text x={m.l + 4} y={y0 + 16} fill={COLOR.index} fontSize="12" fontWeight="600">S&amp;P 500 · the water</text>
        {[1, -1].map(k => <text key={k} x={m.l + 4} y={y(k * span) + (k > 0 ? -6 : 14)} fill="#56627d" fontSize="11">{pct(k * span, 0)}</text>)}
        {cols.map((c, i) => {
          const cx = m.l + cw * (i + .5);
          const lab = c === "monkey" ? "Monkeys" : c === "equal" ? "Equal" : M.A.species[c]?.label || c;
          const group = P.filter(p => c === "monkey" ? p.type === "monkey" : c === "equal" ? p.type === "equal" : p.type === "agent" && p.sp === c);
          return <g key={c}>
            <text x={cx} y={m.t + ph + 22} textAnchor="middle" fill={c === "monkey" ? COLOR.monkey : c === "equal" ? "#fff" : colorOf(group[0] || P[0])} fontSize={phone ? 10 : 12} fontWeight="600">{lab}</text>
            {group.map((p, k) => {
              const off = group.length > 1 ? (k / (group.length - 1) - .5) * Math.min(cw * .6, 14 * group.length) : 0;
              const r = p.type === "agent" ? 7 * Math.max(.7, Math.min(1.6, Math.pow((p.value || M.A.meta.capital) / M.A.meta.capital, 2.2))) : 5;
              const cy = y(M.gap(p)), x = cx + off, col = colorOf(p);
              const ev = { onClick: () => onPick(p.id), onPointerMove: (e: React.PointerEvent) => onHover(p.id, e.clientX, e.clientY), style: { cursor: "pointer" } };
              return <g key={p.id}>
                <line x1={x} x2={x} y1={y0} y2={cy} stroke={col} strokeOpacity=".35" />
                {p.type === "agent"
                  ? <path {...ev} d={`M${x} ${cy - r * 1.4}L${x + r} ${cy}L${x} ${cy + r * 1.4}L${x - r} ${cy}Z`} fill={col} style={{ ...ev.style, filter: M.active.has(p.id) ? `drop-shadow(0 0 6px ${col})` : undefined }} />
                  : <circle {...ev} cx={x} cy={cy} r={r} fill={p.type === "equal" ? "none" : col} stroke={p.type === "equal" ? "#fff" : "none"} strokeWidth="2" />}
              </g>;
            })}
          </g>;
        })}
      </svg>
    </div>
  );
}
