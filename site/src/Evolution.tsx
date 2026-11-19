// EVOLUTION lens (phase 3 data): the tree of life by generation (branches glow while alive, ash at death,
// immigrants ringed), the gene drift across generations, and the ghost tree: the same evolution applied to
// random pickers. If the agents' winners are not clearly better than the ghosts', selection is luck — and the
// screen says so. The evidence line from the engine is always shown.
import { useMemo, useState } from "react";
import { COLOR, nf, pct, sigLabel, SPECIES_COLOR, type Model } from "./data";
import { useData } from "./Intel";

type Node = { name: string; species: string; generation: number; cohort: number; slot: number; immigrant: boolean; parents: string[] | null; born: string; alive: boolean; died: string | null;
  death: { evaluation: number; rank: number; of: number; fitness: number; vs_index: number; value: number } | null; value: number; dna: { weights: Record<string, number> } & Record<string, unknown>;
  gene_delta: { weights: Record<string, number>; management: Record<string, { from: unknown; to: unknown }> } | null };
type Tree = { date: string; rules_version: string; evidence: string; evaluations: { date: string; deaths: string[]; births: { name: string }[] }[]; nodes: Node[]; generations: { generation: number; born: number; alive: number }[] };
type Cmp = { date: string; agents_top5_mean: number; agents_best: number; ghosts_top5_mean: number[]; ghosts_best: number[]; agents_top5_beats_worlds: number };
type Null = { date: string; evidence: string; note: string; worlds: { world: number; count: number }[]; comparison: Cmp[]; replay_identical: boolean };

const FAMILY_KEY: Record<string, string> = { "Trend": "arrow", "Contrarian": "wave", "Value & Quality": "rock", "News": "echo", "Balanced": "plumb", "Mirror": "mirror", "Compass": "compass" };

export function Evolution({ M, onPick }: { M: Model; onPick: (id: string) => void }) {
  const T = useData<Tree>("evolution/tree.json"), G = useData<Null>("evolution/null.json");
  const [hot, setHot] = useState<string | null>(null);
  const spColor = (fam: string) => SPECIES_COLOR[FAMILY_KEY[fam] || fam.toLowerCase()] || "#9aa4b8";
  const signals = Object.keys(M.A.meta.signals || {});

  const layout = useMemo(() => {
    if (!T) return null;
    const gens = Math.max(1, ...T.nodes.map(n => n.generation));
    const W = 640, H = 460, padX = 40, padY = 34;
    const byGen = new Map<number, Node[]>();
    T.nodes.forEach(n => (byGen.get(n.generation) || byGen.set(n.generation, []).get(n.generation)!).push(n));
    const pos = new Map<string, { x: number; y: number }>();
    byGen.forEach((list, g) => {
      list.sort((a, b) => a.slot - b.slot || a.name.localeCompare(b.name));
      list.forEach((n, k) => {
        // a slight spiral: each generation turns a little, so lineages read as rising strands
        const t = (k + .5) / list.length, twist = (g - 1) * .07;
        const x = padX + ((t + twist) % 1) * (W - 2 * padX);
        const y = H - padY - (gens === 1 ? .5 : (g - 1) / (gens - 1)) * (H - 2 * padY);
        pos.set(n.name, { x, y });
      });
    });
    return { W, H, gens, pos };
  }, [T]);

  const drift = useMemo(() => {
    if (!T) return [];
    const gens = [...new Set(T.nodes.map(n => n.generation))].sort((a, b) => a - b);
    return gens.map(g => {
      const list = T.nodes.filter(n => n.generation === g);
      const w: Record<string, number> = {};
      signals.forEach(s => w[s] = list.reduce((a, n) => a + (n.dna?.weights?.[s] || 0), 0) / Math.max(1, list.length));
      return { g, n: list.length, w };
    });
  }, [T, signals]);
  const maxW = Math.max(1, ...drift.flatMap(d => Object.values(d.w)));
  const last = G?.comparison?.[G.comparison.length - 1];
  const alive = T ? T.nodes.filter(n => n.alive).length : 0, dead = T ? T.nodes.length - alive : 0;
  const H = hot && T ? T.nodes.find(n => n.name === hot) : null;
  const goCard = (name: string) => { const p = [...M.A.p, ...(M.A.dead || [])].find(x => x.name === name); if (p) onPick(p.id); };

  return (
    <section className="evo">
      <div className="evo-tree glass">
        <header><span className="lbl">Tree of life{layout ? ` · ${layout.gens} generation${layout.gens > 1 ? "s" : ""}` : ""}</span>
          <span className="lbl faint">{T ? `${alive} alive · ${T.nodes.length - 20 > 0 ? T.nodes.length - 20 : 0} born · ${dead} dead · ${T.evaluations.length} selections` : ""}</span></header>
        {T?.evidence && <div className={"evidence" + (T.evidence.trim().toLowerCase() === "official" ? " ok" : "")}>{T.evidence === "official" ? "Official results: these count as evidence." : T.evidence}</div>}
        {T === undefined ? <div className="empty">Loading…</div> : !T || !layout ? <div className="empty big-empty">The family tree starts with the first selection.</div> :
          <svg viewBox={`0 0 ${layout.W} ${layout.H}`} preserveAspectRatio="xMidYMid meet">
            {Array.from({ length: layout.gens }, (_, g) => {
              const y = layout.H - 34 - (layout.gens === 1 ? .5 : g / (layout.gens - 1)) * (layout.H - 68);
              return (g % Math.max(1, Math.round(layout.gens / 8)) === 0) && <g key={g}><line x1={30} x2={layout.W - 10} y1={y} y2={y} stroke="rgba(130,160,220,.06)" /><text x={4} y={y + 4} fill="#56627d" fontSize="9">G{g + 1}</text></g>;
            })}
            {T.nodes.filter(n => n.parents).flatMap(n => n.parents!.map((pa, k) => {
              const a = layout.pos.get(pa), b = layout.pos.get(n.name); if (!a || !b) return null;
              const on = !hot || hot === n.name || hot === pa;
              return <path key={n.name + k} d={`M${a.x},${a.y} C${a.x},${(a.y + b.y) / 2} ${b.x},${(a.y + b.y) / 2} ${b.x},${b.y}`} fill="none"
                stroke={n.alive ? spColor(n.species) : "#3a4153"} strokeOpacity={on ? (k ? .25 : .55) : .06} strokeWidth={k ? 1 : 1.6} />;
            }))}
            {T.nodes.map(n => {
              const p = layout.pos.get(n.name)!, col = spColor(n.species), r = n.alive ? 4.5 : 3;
              return <g key={n.name} style={{ cursor: "pointer" }} onPointerEnter={() => setHot(n.name)} onPointerLeave={() => setHot(null)} onClick={() => goCard(n.name)}>
                {n.alive && <circle cx={p.x} cy={p.y} r={r + 4} fill={col} opacity=".18" />}
                <circle cx={p.x} cy={p.y} r={r} fill={n.alive ? col : "#2a303d"} stroke={n.immigrant ? "#fff" : n.alive ? "none" : "#4b5367"} strokeWidth={n.immigrant ? 1.4 : 1} />
                {!n.alive && <path d={`M${p.x - 2},${p.y - 2}L${p.x + 2},${p.y + 2}M${p.x + 2},${p.y - 2}L${p.x - 2},${p.y + 2}`} stroke="#6f7686" strokeWidth=".8" />}
              </g>;
            })}
          </svg>}
        <div className="evo-note">
          {H ? <><b>{H.name}</b> · generation {H.generation}{H.immigrant ? " · immigrant" : ""}{H.parents ? ` · parents ${H.parents.join(" × ")}` : " · founder"} · born {H.born}
            {H.death ? <> · <span className="down">died {H.died}</span>, ranked {H.death.rank}/{H.death.of}, {pct(H.death.vs_index)} vs index</> : <> · alive, €{nf(H.value)}</>}
            {H.gene_delta?.weights && <> · genes vs parents: {Object.entries(H.gene_delta.weights).filter(([, v]) => Math.abs(v) >= 1).map(([k, v]) => `${sigLabel(M.A, k)} ${v > 0 ? "+" : ""}${nf(v)}`).join(", ") || "≈ same"}</>}</>
            : <>Founders at the bottom; each generation rises. Lit dots are alive (tap for the card), grey crosses died at a selection, white rings are immigrants (fresh random DNA). Lines join parents and children.</>}
        </div>
      </div>

      <div className="evo-drift glass">
        <header><span className="lbl">Ghost tree · is selection beating luck?</span><span className="lbl faint">{G ? `${G.worlds.length} ghost worlds` : ""}</span></header>
        {G === undefined ? <div className="empty">Loading…</div> : !G ? <div className="empty">No ghost worlds yet.</div> : !G.comparison.length ?
          <div className="ghost-wait">No selection yet. The ghosts evolve with the agents: same rules, random picks.<br /><span className="faint">{G.note}</span></div> :
          <GhostChart G={G} />}
        {last && <div className={"verdict " + (last.agents_top5_beats_worlds >= .9 ? "up" : "")}>
          Agents' top 5 beat <b className="num">{nf(last.agents_top5_beats_worlds * 10)}</b> of 10 ghost worlds at the last selection.
          {last.agents_top5_beats_worlds < .9 ? " Not clearly better than luck yet." : " Clearly better than the ghosts so far."}
        </div>}
        <header style={{ marginTop: 6 }}><span className="lbl">Gene drift · what each generation values</span><span className="lbl faint">mean DNA weight (%)</span></header>
        <div className="heat" style={{ gridTemplateColumns: `100px repeat(${Math.max(1, drift.length)}, minmax(14px, 1fr))` }}>
          <span />
          {drift.map(d => <span key={d.g} className="hh" title={`generation ${d.g}: ${d.n} agents`}>{drift.length > 12 ? (d.g % 5 === 1 ? d.g : "") : "G" + d.g}</span>)}
          {signals.map(s => {
            const ev = M.A.meta.evidence?.[s]?.status;
            return [
              <span key={s + "l"} className="hl" title={ev ? "evidence: " + ev : "evidence: not yet measured"}>{sigLabel(M.A, s)}{ev ? <i className={"ev " + ev} /> : null}</span>,
              ...drift.map(d => <span key={s + d.g} className="hc num" style={{ background: `rgba(159,216,255,${d.w[s] / maxW * .75})` }} title={`G${d.g} · ${sigLabel(M.A, s)} ${nf(d.w[s], 1)}%`}>{drift.length <= 8 && d.w[s] ? nf(d.w[s], 0) : ""}</span>),
            ];
          })}
        </div>
        <div className="evo-note">A colour drifting along a row means the arena is learning to value that signal. The dot beside a signal is its evidence status in the Lab.</div>
      </div>
    </section>
  );
}

function GhostChart({ G }: { G: Null }) {
  const C = G.comparison, W = 420, H = 150, m = 28;
  const all = C.flatMap(c => [c.agents_top5_mean, ...c.ghosts_top5_mean]);
  let lo = Math.min(0, ...all), hi = Math.max(0, ...all); if (hi - lo < .01) { hi += .005; lo -= .005; }
  const X = (i: number) => m + (W - m - 6) * (C.length === 1 ? .5 : i / (C.length - 1)), Y = (v: number) => 8 + (H - 24) * (1 - (v - lo) / (hi - lo));
  const band = C.map((c, i) => [i, Math.min(...c.ghosts_top5_mean), Math.max(...c.ghosts_top5_mean)] as const);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="ghostchart" preserveAspectRatio="xMidYMid meet">
      <line x1={m} x2={W - 6} y1={Y(0)} y2={Y(0)} stroke="rgba(130,160,220,.25)" />
      <text x={m - 4} y={Y(hi) + 8} textAnchor="end" fill="#56627d" fontSize="9">{pct(hi, 0)}</text>
      <text x={m - 4} y={Y(lo)} textAnchor="end" fill="#56627d" fontSize="9">{pct(lo, 0)}</text>
      {C.length > 1 && <polygon points={band.map(([i, , b]) => `${X(i)},${Y(b)}`).join(" ") + " " + band.slice().reverse().map(([i, a]) => `${X(i)},${Y(a)}`).join(" ")} fill={COLOR.luck} opacity=".18" />}
      {C.length > 1 && <polyline points={C.map((c, i) => `${X(i)},${Y(c.agents_top5_mean)}`).join(" ")} fill="none" stroke={COLOR.index} strokeWidth="2" />}
      {C.map((c, i) => <circle key={i} cx={X(i)} cy={Y(c.agents_top5_mean)} r="2.5" fill={COLOR.index}><title>{`${c.date}: agents top-5 ${pct(c.agents_top5_mean)} · ghosts ${pct(Math.min(...c.ghosts_top5_mean))} to ${pct(Math.max(...c.ghosts_top5_mean))}`}</title></circle>)}
      <text x={W - 6} y={H - 3} textAnchor="end" fill="#56627d" fontSize="9">blue = agents' top 5 · grey = top 5 of each ghost world</text>
    </svg>
  );
}
