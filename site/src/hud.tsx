import { COLOR, colorOf, day, dayY, label, nf, pct, SPECIES_COLOR, tone, type Model, type Participant } from "./data";
import type { Tier } from "./quality";

export type TipState = { id: string; x: number; y: number } | null;

export function Shape({ p }: { p: Participant }) {
  const c = colorOf(p);
  return p.type === "agent" ? <span className="gem" style={{ background: c }} />
    : p.type === "equal" ? <span className="dot" style={{ border: "2px solid #fff", background: "none" }} />
      : <span className="dot" style={{ background: c }} />;
}

export function Top({ M, tier, setTier, gl, onHelp }: { M: Model; tier: Tier; setTier: (t: Tier) => void; gl: boolean; onHelp: () => void }) {
  const n = Math.max(0, M.A.meta.dates.length - 1);
  const live = M.A.meta.mode === "live";
  return (
    <header className="top">
      <div className="brand">
        <span className="mark" aria-hidden="true" />
        <b>ARENA</b>
        <span className="chip where" title={M.A.meta.updated ? "Data as of the market close of this day" : ""}>
          <span className="live" />{live ? "LIVE" : "TRIAL"} · <span className="num">DAY {n}</span> · {M.A.meta.updated ? dayY(M.A.meta.updated) : "opens after the first night"}
        </span>
      </div>
      <div className="tools">
        <div className="seg" role="group" aria-label="Quality">
          {(["ultra", "high", "lite"] as Tier[]).map(t => (
            <button key={t} aria-pressed={tier === t} disabled={!gl && t !== "lite"} onClick={() => setTier(t)}
              title={t === "ultra" ? "Full effects" : t === "high" ? "Lighter 3D" : "2D view, no 3D"}>{t === "lite" ? "2D" : t.toUpperCase()}</button>
          ))}
        </div>
        <button className="round" aria-label="How to read" title="How to read" onClick={onHelp}>?</button>
      </div>
    </header>
  );
}

export function Kpis({ M, onPick }: { M: Model; onPick: (id: string) => void }) {
  const idx = M.index, best = M.agents[0];
  const above = M.agents.filter(p => (p.vsIdx || 0) > 0).length, total = M.agents.length || 1;
  const mAbove = M.monkeys.filter(p => (p.vsIdx || 0) > 0).length;
  const L = M.A.luck;
  return (
    <section className="kpis" aria-label="At a glance">
      {idx && (
        <button className="kpi glass hot" style={{ textAlign: "left" }} onClick={() => onPick(idx.id)} title="The benchmark: S&P 500 with dividends, in euros. It is the water line.">
          <div className="lbl"><span className="wave" />S&P 500</div>
          <div className={"v num " + tone(idx.ret)}>{pct(idx.ret)}<small>since {day(idx.from)}</small></div>
        </button>
      )}
      <div className="kpi glass" title="Agents beating the S&P 500 since day zero">
        <div className="lbl">Above water</div>
        <div className="v num">{above}<small>/ {M.agents.length}</small></div>
        <div className="bar"><i style={{ width: `${above / total * 100}%`, background: COLOR.index }} /></div>
      </div>
      {M.lucky != null && L ? (
        <div className="kpi glass" title={`Agents doing better than 95% of ${nf(L.n)} random monkeys with the same rules. Only these show more than luck.`}>
          <div className="lbl">Above the luck band</div>
          <div className="v num">{M.lucky}<small>/ {M.agents.length}</small></div>
          <div className="bar"><i style={{ width: `${M.lucky / total * 100}%`, background: COLOR.luck }} /></div>
        </div>
      ) : (
        <div className="kpi glass" title="Monkeys pick at random. If they beat the index too, beating it proves little.">
          <div className="lbl">Monkeys above water</div>
          <div className="v num">{mAbove}<small>/ {M.monkeys.length}</small></div>
        </div>
      )}
      {best && M.moved ? (
        <button className="kpi glass hot" style={{ textAlign: "left" }} onClick={() => onPick(best.id)}>
          <div className="lbl"><Shape p={best} />Leader</div>
          <div className="v" style={{ fontSize: 22, fontWeight: 600 }}>{best.name}<small className={"num " + tone(best.vsIdx)}>{pct(best.vsIdx)}</small></div>
        </button>
      ) : (
        <div className="kpi glass"><div className="lbl">Last night</div><div className="v num">{M.A.day ? M.A.day.buys + M.A.day.sells : 0}<small>trades</small></div></div>
      )}
    </section>
  );
}

export function Board({ M, open, hover, onPick, onHover }: { M: Model; open: boolean; hover: string | null; onPick: (id: string) => void; onHover: (id: string | null) => void }) {
  const rows = [...M.agents, ...(M.index ? [M.index] : []), ...(M.equal ? [M.equal] : [])];
  const max = Math.max(1e-4, ...rows.map(p => Math.abs(M.gap(p))), ...M.monkeys.map(p => Math.abs(M.gap(p))));
  const mid = M.monkeys.length ? M.monkeys.slice().sort((a, b) => M.gap(b) - M.gap(a))[Math.floor((M.monkeys.length - 1) / 2)] : null;
  const luckTop = M.luck ? M.luck[1] : null;
  const Row = ({ p, cls = "", name = label(p) }: { p: Participant; cls?: string; name?: string }) => {
    const g = M.gap(p), w = Math.abs(g) / max * 20;
    return (
      <button className={`row ${cls} ${hover === p.id ? "hl" : ""}`} onClick={() => onPick(p.id)} onPointerEnter={() => onHover(p.id)} onPointerLeave={() => onHover(null)}>
        <span className="n num">{M.rank[p.id] ?? ""}</span><Shape p={p} /><span className="nm">{name}</span>
        {p.type === "index" ? <><span className="trk" /><span className="pc mute">water</span></> : <>
          <span className="trk"><i style={{ [g >= 0 ? "left" : "right"]: "50%", width: w, background: g >= 0 ? COLOR.up : COLOR.down } as React.CSSProperties} /></span>
          <span className={"pc num " + tone(g)}>{M.moved ? pct(g) : "±0%"}</span></>}
      </button>
    );
  };
  return (
    <aside className={"board glass" + (open ? " open" : "")} aria-label="Ranking">
      <header><span className="lbl">{M.scored ? "Ranking · score" : "Ranking"}</span><span className="lbl">vs S&P 500</span></header>
      <div className="rows">
        {M.agents.map((p, i) => {
          const next = M.agents[i + 1];
          const cross = luckTop != null && M.gap(p) > luckTop && next && M.gap(next) <= luckTop;
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

export function Podium({ M, onPick }: { M: Model; onPick: (id: string) => void }) {
  if (!M.agents.length) return <section className="podium" />;
  if (!M.moved) return (
    <section className="podium" aria-label="Podium">
      <span className="lbl">Podium</span>
      <div className="glass" style={{ padding: "13px 20px", textAlign: "center" }}>
        <div style={{ fontWeight: 600 }}>Everyone starts at <span className="num">€{nf(M.A.meta.capital)}</span></div>
        <div className="mute" style={{ fontSize: 12, marginTop: 4 }}>First trades at the next market open</div>
      </div>
    </section>
  );
  const top = [M.agents[1], M.agents[0], M.agents[2]].filter(Boolean);
  const merit = M.agents.slice(0, 3).some(p => p.merit);
  return (
    <section className="podium" aria-label="Podium">
      <span className={"badge " + (merit ? "merit" : "prov")} title="Merit only after enough history, beating the index and 95% of the monkeys">{merit ? "Merit" : "Provisional"}</span>
      <div className="steps">
        {top.map(p => (
          <button key={p.id} className={`step glass hot p${M.rank[p.id]}`} onClick={() => onPick(p.id)}>
            <div className="who"><Shape p={p} />{p.name}</div>
            <div className={"pct num " + tone(p.vsIdx)}>{pct(p.vsIdx)}</div>
            <div className="base">{M.rank[p.id]}</div>
          </button>
        ))}
      </div>
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

export function Tip({ M, tip }: { M: Model; tip: TipState }) {
  if (!tip) return null;
  const p = M.byId[tip.id]; if (!p) return null;
  const x = Math.min(tip.x, innerWidth - 300), y = Math.min(tip.y, innerHeight - 90);
  return (
    <div className="tip" style={{ left: x, top: y }}>
      <b>{label(p)}</b>{p.type === "agent" && p.sp && <span className="mute"> · {M.A.species[p.sp]?.label}</span>}<br />
      <span className="num">€{nf(p.value)}</span> · <span className={"num " + tone(p.ret)}>{pct(p.ret)}</span>
      {p.type !== "index" && <> · vs index <span className={"num " + tone(p.vsIdx)}>{pct(p.vsIdx)}</span></>}
      {p.pctAll != null && <> · beats <span className="num">{nf(p.pctAll * 100)}%</span> of monkeys</>}
    </div>
  );
}

export function Help({ M, onClose }: { M: Model; onClose: () => void }) {
  return (
    <div className="veil" onClick={onClose}>
      <div className="help glass" role="dialog" aria-modal="true" aria-label="How to read">
        <h2>How to read the arena</h2>
        <div><span className="ic"><span className="gem" style={{ background: SPECIES_COLOR.arrow }} /></span><span><b>Each crystal is an agent</b>Colour = species. Bigger = more money. Glowing = traded at the last open.</span></div>
        <div><span className="ic"><span className="wave" /></span><span><b>The water is the S&P 500</b>Above the water = beating the index. Below = losing to it.</span></div>
        <div><span className="ic"><span className="dot" style={{ background: COLOR.luck }} /></span><span><b>The grey band is luck</b>{nf(M.luckN)} monkeys follow the same rules but pick at random; 90% end inside the band. Only agents above it show more than luck.</span></div>
        <div><span className="ic"><span className="dot" style={{ border: "2px solid #fff" }} /></span><span><b>White ring: equal weight</b>Every company in equal parts, never touched.</span></div>
        <div><span className="ic">◆</span><span><b>Podium</b>Ranked by return over the index per unit of extra risk. "Merit" only after enough history and beating 95% of the monkeys.</span></div>
        <div><span className="ic">↗</span><span><b>Tap anything</b>Opens its card: value, DNA, holdings and every move with its reason.</span></div>
        <p>Each agent starts with €{nf(M.A.meta.capital)} of simulated money on the S&P 100. Decisions at night, filled at the next open, with real costs. Not investment advice. Rules v{M.A.meta.rules} · engine {M.A.meta.engine}.</p>
      </div>
    </div>
  );
}
