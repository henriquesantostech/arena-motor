// JOURNAL lens: the daily newspaper. One page per night, built only from what was known that night,
// every item with its source. Tabs: Front · Markets · World · Companies · People · Arena.
import { useEffect, useState } from "react";
import { COLOR, day, dayY, nf, pct, ROOT, tone, type Model } from "./data";
import { Shape } from "./hud";

type Cite = { id: string; title?: string; url?: string; source?: string; published_at?: string };
type Page = {
  date: string;
  front: { k: string; title: string; v?: number; t?: string; id?: string; src: string }[];
  markets: { spx: number | null; eurusd: number | null; above_ma: boolean | null; sectors: { sector: string; ret: number; n: number }[]; movers: { t: string; name: string; sector: string; ret: number }[] };
  companies: { traded: { t: string; name: string; buys: number; sells: number }[]; movers: { t: string; name: string; sector: string; ret: number }[] };
  arena: { fills: number; buys: number; sells: number; agents: number; best: { id: string; name: string; ret: number }[]; worst: { id: string; name: string; ret: number }[]; excluded: string[]; rule_changes: unknown };
  world: null | { as_of: string; model: string; headline?: string; items: { topic: string; summary: string; cites: Cite[] }[]; markets?: string; sectors: { sector: string; score: number; reason: string; cites: Cite[] }[]; watch: string[] };
  people: { kind: string; person_name: string; role?: string; ticker: string; action: string; size_low?: number; size_high?: number; traded_on?: string; disclosed_at?: string; delay_days?: number; note?: string }[];
  sources: Record<string, { kind: string; label: string; sha256?: string | null; as_of?: string }>;
};
const cache = new Map<string, Promise<Page>>();
const load = (d: string) => {
  if (!cache.has(d)) cache.set(d, fetch(`${ROOT}data/journal/${d}.json`).then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json(); }));
  return cache.get(d)!;
};
const TABS = ["front", "markets", "world", "companies", "people", "arena"] as const;
type Tab = typeof TABS[number];

export function Journal({ M, i, setI, onPick }: { M: Model; i: number; setI: (n: number) => void; onPick: (id: string) => void }) {
  const d = M.A.meta.dates[i];
  const [page, setPage] = useState<Page | null>(null);
  const [err, setErr] = useState(false);
  const [tab, setTab] = useState<Tab>("front");
  useEffect(() => { if (!d) return; setErr(false); load(d).then(setPage).catch(() => { setPage(null); setErr(true); }); }, [d]);
  if (!d) return <div className="journal glass"><div className="empty">The journal starts after the first night.</div></div>;
  const P = page && page.date === d ? page : null;
  return (
    <section className="journal glass" aria-label="Journal">
      <header className="jhead">
        <div className="jdate">
          <button className="round" aria-label="Previous day" disabled={i <= 0} onClick={() => setI(i - 1)}>‹</button>
          <div><div className="lbl">The Arena Journal · day {i}</div><div className="jt">{dayY(d)}</div></div>
          <button className="round" aria-label="Next day" disabled={i >= M.last} onClick={() => setI(i + 1)}>›</button>
        </div>
        <nav className="seg jtabs">{TABS.map(t => <button key={t} aria-pressed={tab === t} onClick={() => setTab(t)}>{t.toUpperCase()}</button>)}</nav>
      </header>
      <div className="jbody">
        {!P ? <div className="empty">{err ? "No journal page for this day." : "Loading…"}</div>
          : tab === "front" ? <Front P={P} M={M} onPick={onPick} go={setTab} />
            : tab === "markets" ? <Markets P={P} />
              : tab === "world" ? <World P={P} />
                : tab === "companies" ? <Companies P={P} />
                  : tab === "people" ? <People P={P} />
                    : <ArenaTab P={P} M={M} onPick={onPick} />}
      </div>
      {P && <footer className="jsrc">
        <span className="lbl">Sources</span>
        {Object.entries(P.sources).map(([k, s]) => <span key={k} className="chip" title={s.sha256 ? "SHA-256 " + s.sha256 : s.as_of || ""}>{s.label}{s.sha256 ? <code>{s.sha256.slice(0, 10)}…</code> : null}</span>)}
      </footer>}
    </section>
  );
}

function Bar({ v, max }: { v: number; max: number }) {
  const w = Math.min(50, Math.abs(v) / (max || 1) * 50);
  return <span className="dbar"><i style={{ [v >= 0 ? "left" : "right"]: "50%", width: w + "%", background: v >= 0 ? COLOR.up : COLOR.down } as React.CSSProperties} /></span>;
}

function Front({ P, M, onPick, go }: { P: Page; M: Model; onPick: (id: string) => void; go: (t: Tab) => void }) {
  if (!P.front.length) return <div className="empty">A quiet night: no market move yet.</div>;
  return (
    <div className="jfront">
      {P.front.map((f, k) => (
        <button key={k} className={"jstory" + (k === 0 ? " lead" : "")} onClick={() => f.id ? onPick(f.id) : go(f.k === "world" ? "world" : f.k === "people" ? "people" : f.k === "arena" ? "arena" : f.k === "company" ? "companies" : "markets")}>
          <span className="lbl">{f.k}</span>
          <span className="jh">{f.title}</span>
          {f.v != null && <span className={"num big " + tone(f.v)}>{pct(f.v, 1)}</span>}
          {f.id && M.byId[f.id] && <span className="mute"><Shape p={M.byId[f.id]} /> open card</span>}
          <span className="faint small">source: {P.sources[f.src]?.label || f.src}</span>
        </button>
      ))}
    </div>
  );
}

function Markets({ P }: { P: Page }) {
  const m = P.markets, max = Math.max(1e-4, ...m.sectors.map(s => Math.abs(s.ret)));
  return (
    <div className="jgrid">
      <div className="jcard">
        <div className="lbl">S&P 500 (USD)</div><div className={"num big " + tone(m.spx)}>{pct(m.spx, 2)}</div>
        <div className="row3"><div><div className="lbl">EUR/USD</div><div className="num">{nf(m.eurusd, 4)}</div></div>
          <div><div className="lbl">200-day</div><div className={m.above_ma === false ? "down" : "up"}>{m.above_ma === false ? "below" : "above"}</div></div><div /></div>
      </div>
      <div className="jcard span2">
        <div className="lbl">Sectors · average move of their S&P 100 companies</div>
        {m.sectors.map(s => <div key={s.sector} className="jrow"><span>{s.sector}</span><Bar v={s.ret} max={max} /><span className={"num " + tone(s.ret)}>{pct(s.ret, 2)}</span></div>)}
      </div>
      <Movers list={m.movers} />
    </div>
  );
}

function Movers({ list }: { list: Page["markets"]["movers"] }) {
  return (
    <div className="jcard span3">
      <div className="lbl">Biggest moves in the universe</div>
      <div className="jtiles">{list.map(x => (
        <div key={x.t} className="jtile" style={{ background: x.ret >= 0 ? `rgba(62,224,143,${.1 + Math.min(x.ret / .08, 1) * .4})` : `rgba(255,107,107,${.1 + Math.min(-x.ret / .08, 1) * .4})` }} title={`${x.name} · ${x.sector}`}>
          <b>{x.t}</b><span className="num">{pct(x.ret, 1)}</span><small>{x.name}</small>
        </div>))}</div>
    </div>
  );
}

function Companies({ P }: { P: Page }) {
  const c = P.companies, max = Math.max(1, ...c.traded.map(x => x.buys + x.sells));
  return (
    <div className="jgrid">
      <div className="jcard span2">
        <div className="lbl">Most traded by the agents at the open</div>
        {c.traded.length ? c.traded.map(x => (
          <div key={x.t} className="jrow"><span><b>{x.t}</b> <span className="mute">{x.name}</span></span>
            <span className="stack"><i style={{ width: x.buys / max * 100 + "%", background: COLOR.up }} /><i style={{ width: x.sells / max * 100 + "%", background: COLOR.down }} /></span>
            <span className="num"><span className="up">{x.buys}</span> / <span className="down">{x.sells}</span></span></div>
        )) : <div className="empty">No trades at this open.</div>}
      </div>
      <Movers list={c.movers} />
    </div>
  );
}

function World({ P }: { P: Page }) {
  const w = P.world;
  if (!w) return <div className="empty big-empty">The World Brief arrives with the intelligence layer (phase 2). Until then this tab stays empty rather than guessing.</div>;
  if ((w as { incomplete?: boolean }).incomplete) return <div className="empty big-empty">Brief incomplete today: the World Brief was cut off, so it is not shown.</div>;
  const C = ({ cs }: { cs: Cite[] }) => <span className="cites">{cs.map(c => c.url ? <a key={c.id} href={c.url} target="_blank" rel="noreferrer noopener" title={c.title || c.id}>[{c.source || c.id.slice(0, 6)}]</a> : <span key={c.id} title={c.id}>[{c.id.slice(0, 8)}]</span>)}</span>;
  return (
    <div className="jgrid">
      {w.headline && <div className="jcard span3 lead"><div className="lbl">Headline · {w.model}</div><div className="jh">{w.headline}</div></div>}
      <div className="jcard span2">{w.items.map((x, k) => <div key={k} className="witem"><b>{x.topic}</b><span>{x.summary}</span><C cs={x.cites} /></div>)}</div>
      <div className="jcard">
        <div className="lbl">Sector winds (−2 to +2)</div>
        {w.sectors.map(s => <div key={s.sector} className="jrow" title={s.reason}><span>{s.sector}</span><Bar v={s.score} max={2} /><span className={"num " + tone(s.score)}>{s.score > 0 ? "+" : ""}{s.score}</span></div>)}
      </div>
    </div>
  );
}

function People({ P }: { P: Page }) {
  if (!P.people.length) return <div className="empty big-empty">No disclosures published this day.</div>;
  return (
    <div className="jgrid">
      <div className="jcard span3">
        <div className="lbl">Disclosures · a pattern worth noting, never an accusation</div>
        {P.people.map((a, k) => (
          <div key={k} className="jrow people">
            <span><b>{a.person_name}</b> <span className="mute">{a.role || a.kind}</span></span>
            <span className={"k-" + (a.action === "buy" ? "buy" : "sell")}>{a.action}</span>
            <b>{a.ticker}</b>
            <span className="num mute">{a.size_low != null ? `$${nf(a.size_low)}–${nf(a.size_high)}` : ""}</span>
            <span className="badge" title={`traded ${a.traded_on}, disclosed ${a.disclosed_at}`}>delay {a.delay_days ?? "?"}d</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ArenaTab({ P, M, onPick }: { P: Page; M: Model; onPick: (id: string) => void }) {
  const a = P.arena;
  const Line = ({ x }: { x: { id: string; name: string; ret: number } }) => {
    const p = M.byId[x.id];
    return <button className="jrow" onClick={() => onPick(x.id)}><span>{p && <Shape p={p} />} {x.name}</span><Bar v={x.ret} max={.05} /><span className={"num " + tone(x.ret)}>{pct(x.ret, 2)}</span></button>;
  };
  return (
    <div className="jgrid">
      <div className="jcard">
        <div className="lbl">At the open</div>
        <div className="row3"><div><div className="lbl">Buys</div><div className="num big up">{a.buys}</div></div><div><div className="lbl">Sells</div><div className="num big down">{a.sells}</div></div><div><div className="lbl">Agents</div><div className="num big">{a.agents}</div></div></div>
        <div className="small mute">{a.excluded.length ? `Set aside tonight (data check): ${a.excluded.join(", ")}` : "All companies passed the data checks."}</div>
        {a.rule_changes ? <div className="small" style={{ color: "var(--wave)" }}>Rule change took effect this day.</div> : null}
      </div>
      <div className="jcard"><div className="lbl">Best agents of the day</div>{a.best.map(x => <Line key={x.id} x={x} />)}</div>
      <div className="jcard"><div className="lbl">Worst agents of the day</div>{a.worst.map(x => <Line key={x.id} x={x} />)}</div>
      <div className="jcard span3 small mute">{day(P.date)}: values at the close; trades filled at that morning's open.</div>
    </div>
  );
}
