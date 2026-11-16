// EVOLUTION lens: the tree of life (founders by species, branches glow while alive, ash at death),
// the gene-drift heatmap (population weights per signal, by generation and by species) and the ghost
// tree (the monkeys: same rules, random picks; the null evolution runs beside the real one).
import { useMemo, useState } from "react";
import { COLOR, nf, pct, sigLabel, SPECIES_COLOR, type Model, type Participant } from "./data";

export function Evolution({ M, onPick }: { M: Model; onPick: (id: string) => void }) {
  const gen = (M.A.meta as { generation?: number }).generation || 1;
  const [hot, setHot] = useState<string | null>(null);
  const agents = M.A.p.filter(p => p.type === "agent");
  const signals = Object.keys(M.A.meta.signals || {});
  const bySp = useMemo(() => {
    const o: Record<string, Participant[]> = {};
    agents.forEach(p => (o[p.sp || ""] ||= []).push(p));
    return o;
  }, [agents]);
  const mean = (list: Participant[], s: string) => list.length ? list.reduce((a, p) => a + (p.dna?.w[s] || 0), 0) / list.length : 0;
  const maxW = Math.max(1, ...signals.flatMap(s => M.species.map(sp => mean(bySp[sp] || [], s))));
  const dead = 0, born = agents.filter(p => p.parents && p.parents.length).length;

  // tree of life: root at the bottom centre, one branch per species fanning upward, founders as leaves
  const W = 560, H = 420, cx = W / 2, cy = H - 40;
  const S = M.species, ghosts = M.monkeys;
  const leaf = (si: number, k: number, n: number, r: number) => {
    const a = Math.PI * (0.12 + 0.76 * (si + (n === 1 ? 0.5 : (k + 0.5) / n) / 1) / S.length);
    return [cx - Math.cos(a) * r, cy - Math.sin(a) * r * 0.95] as const;
  };
  return (
    <section className="evo" aria-label="Evolution">
      <div className="evo-tree glass">
        <header><span className="lbl">Tree of life · generation {gen}</span><span className="lbl faint">{agents.length} alive · {born} born · {dead} dead</span></header>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
          <defs>
            <radialGradient id="rootg"><stop offset="0" stopColor="#9fd8ff" stopOpacity=".9" /><stop offset="1" stopColor="#9fd8ff" stopOpacity="0" /></radialGradient>
          </defs>
          {/* ghost tree: the monkeys, faint, mirrored on the far ring */}
          {ghosts.map((g, k) => {
            const a = Math.PI * (0.06 + 0.88 * (k + 0.5) / ghosts.length), r = 330;
            const x = cx - Math.cos(a) * r, y = cy - Math.sin(a) * r * 0.95;
            return <g key={g.id} opacity=".4">
              <path d={`M${cx},${cy} Q${cx - Math.cos(a) * r * .45},${cy - 40} ${x},${y}`} fill="none" stroke={COLOR.monkey} strokeDasharray="2 5" />
              <circle cx={x} cy={y} r={4} fill={COLOR.monkey} />
            </g>;
          })}
          {/* species branches and founders */}
          {S.map((sp, si) => {
            const list = (bySp[sp] || []).slice().sort((a, b) => a.name.localeCompare(b.name)), col = SPECIES_COLOR[sp] || "#9aa4b8";
            const [bx, by] = leaf(si, 0, 1, 120);
            return <g key={sp}>
              <path d={`M${cx},${cy} C${cx},${cy - 60} ${bx},${by + 50} ${bx},${by}`} fill="none" stroke={col} strokeWidth="3" opacity=".75" style={{ filter: `drop-shadow(0 0 6px ${col})` }} />
              <text x={bx} y={by + 22} textAnchor="middle" fill={col} fontSize="11" fontWeight="600" letterSpacing="2">{M.A.species[sp]?.label.toUpperCase()}</text>
              {list.map((p, k) => {
                const [x, y] = leaf(si, k, list.length, 235), r = 5 + 6 * Math.max(0, Math.min(1.5, p.value / M.A.meta.capital)) ** 2 / 2.25;
                const on = hot === p.id;
                return <g key={p.id} style={{ cursor: "pointer" }} onClick={() => onPick(p.id)} onPointerEnter={() => setHot(p.id)} onPointerLeave={() => setHot(null)}>
                  <path d={`M${bx},${by} Q${(bx + x) / 2},${by - 30} ${x},${y}`} fill="none" stroke={col} strokeWidth={on ? 2.5 : 1.5} opacity=".7" />
                  <circle cx={x} cy={y} r={r + (on ? 3 : 0)} fill={col} style={{ filter: `drop-shadow(0 0 ${on ? 12 : 7}px ${col})` }} />
                  <text x={x} y={y - r - 5} textAnchor="middle" fill="#dfe6f5" fontSize={on ? 12 : 9.5} fontWeight={on ? 600 : 400} opacity={on ? 1 : .6}>{on ? p.name : p.name.replace(/^.*-/, "")}</text>
                </g>;
              })}
            </g>;
          })}
          <circle cx={cx} cy={cy} r={26} fill="url(#rootg)" />
          <circle cx={cx} cy={cy} r={6} fill="#e7eefc" />
          <text x={cx} y={cy + 24} textAnchor="middle" fill="#8b98b5" fontSize="10.5" letterSpacing="2">GENERATION {gen}</text>
        </svg>
        <div className="evo-note">
          {gen === 1 ? <>Selection has not started: all {agents.length} founders are alive. The weakest are removed and the strongest have offspring after the trial. The faint grey branches are the <b>ghost tree</b>: monkeys with the same rules and random picks. If evolved monkeys come to look like evolved agents, selection is luck, and this screen will say so.</>
            : <>Ghost tree: monkeys evolved by the same process. If they look alike, selection is luck.</>}
        </div>
        {hot && M.byId[hot] && <div className="genetip" style={{ left: 16, bottom: 16 }}><b>{hot && M.byId[hot].name}</b> · {pct(M.byId[hot].ret)} · born {M.byId[hot].born} · {M.byId[hot].parents?.length ? "parents " + M.byId[hot].parents!.join(", ") : "founder"}</div>}
      </div>

      <div className="evo-drift glass">
        <header><span className="lbl">Gene drift · what the population values</span><span className="lbl faint">mean DNA weight (%)</span></header>
        <div className="heat" style={{ gridTemplateColumns: `110px repeat(${M.species.length}, 1fr) 1fr` }}>
          <span />
          {M.species.map(sp => <span key={sp} className="hh" style={{ color: SPECIES_COLOR[sp] }}>{M.A.species[sp]?.label}</span>)}
          <span className="hh">Gen {gen}</span>
          {signals.map(s => {
            const ev = M.A.meta.evidence?.[s]?.status;
            return [
              <span key={s + "l"} className="hl" title={ev ? "evidence: " + ev : "evidence: not yet measured"}>{sigLabel(M.A, s)}{ev ? <i className={"ev " + ev} /> : null}</span>,
              ...M.species.map(sp => { const v = mean(bySp[sp] || [], s); return <span key={s + sp} className="hc num" style={{ background: `color-mix(in srgb, ${SPECIES_COLOR[sp]} ${Math.round(v / maxW * 85)}%, transparent)` }} title={`${M.A.species[sp]?.label} · ${sigLabel(M.A, s)} ${nf(v, 1)}%`}>{v ? nf(v, 0) : ""}</span>; }),
              (() => { const v = mean(agents, s); return <span key={s + "g"} className="hc num" style={{ background: `rgba(159,216,255,${v / maxW * .7})` }} title={`population ${nf(v, 1)}%`}>{v ? nf(v, 0) : ""}</span>; })(),
            ];
          })}
        </div>
        <div className="evo-note">Columns grow one per generation as evolution runs: a colour drifting across a row means the arena is learning to value that signal. The dot beside a signal is its evidence status in the Signal Lab.</div>
        <div className="row3 evo-stats">
          <div><div className="lbl">Founders</div><div className="num">{agents.length}</div></div>
          <div><div className="lbl">Species</div><div className="num">{M.species.length}</div></div>
          <div><div className="lbl">Ghost monkeys</div><div className="num">{M.monkeys.length}</div></div>
        </div>
      </div>
    </section>
  );
}
