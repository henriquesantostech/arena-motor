// TODAY lens: a ring of live widgets around the world. Tapping a widget opens what it summarises.
import { COLOR, colorOf, day, eur, label, nf, pct, tone, type Model } from "./data";
import { Shape, type Lens } from "./hud";

export function Today({ M, onPick, setLens }: { M: Model; onPick: (id: string) => void; setLens: (l: Lens) => void }) {
  const A = M.A, d = A.day, i = M.last, L = A.luck;
  const idx = M.index;
  const daily = M.agents.map(p => ({ p, ch: i > 0 ? M.valueAt(p, i) / M.valueAt(p, i - 1) - 1 : 0 })).sort((a, b) => b.ch - a.ch);
  const best = M.agents.slice().sort((a, b) => b.ret - a.ret)[0];
  const traded = (A.fillsByDay?.[A.meta.dates[i]] || []).length;
  const top = M.agents.slice(0, 3);
  // luck meter: where the best agent sits between the median monkey and the best of N monkeys
  const lo = L?.p05 ?? -0.05, hi = Math.max(L?.best ?? 0.05, best?.ret ?? 0, (L?.p95 ?? 0) + 0.01);
  const pos = (x: number) => Math.max(0, Math.min(100, (x - lo) / (hi - lo || 1) * 100));
  return (
    <div className="today">
      <section className="w glass hot" onClick={() => idx && onPick(idx.id)}>
        <header><span className="lbl"><span className="wave" />Market pulse</span><span className="lbl faint">{day(A.meta.updated)}</span></header>
        <div className="big num"><span className={tone(d?.spx)}>{pct(d?.spx, 2)}</span><small>S&P 500 today</small></div>
        <div className="row3">
          <div><div className="lbl">Since start</div><div className={"num " + tone(idx ? M.retAt(idx, i) : 0)}>{pct(idx ? M.retAt(idx, i) : 0)}</div></div>
          <div><div className="lbl">EUR/USD</div><div className="num">{nf(d?.eurusd, 4)}</div></div>
          <div title="Above its 200-day average: no brake. Below: cautious agents invest less."><div className="lbl">Trend</div><div className={d?.aboveMa200 === false ? "down" : "up"}>{d?.aboveMa200 === false ? "below 200d" : "above 200d"}</div></div>
        </div>
      </section>

      <section className="w glass hot" onClick={() => setLens("arena")}>
        <header><span className="lbl">Podium</span><span className={"badge " + (top.some(p => p.merit) ? "merit" : "prov")}>{top.some(p => p.merit) ? "Merit" : "Provisional"}</span></header>
        {M.moved ? top.map((p, k) => (
          <button key={p.id} className="line" onClick={e => { e.stopPropagation(); onPick(p.id); }}>
            <span className="medal num" style={{ background: [COLOR.gold, COLOR.silver, COLOR.bronze][k] }}>{k + 1}</span><Shape p={p} /><span>{p.name}</span>
            <span className={"num " + tone(p.vsIdx)}>{pct(p.vsIdx)}</span>
          </button>
        )) : <div className="mute">Everyone starts at €{nf(A.meta.capital)}</div>}
      </section>

      <section className="w glass" title="Where the best agent sits against the random monkeys. Inside the grey band = indistinguishable from luck.">
        <header><span className="lbl">Luck meter</span><span className="lbl faint">{nf(M.luckN)} monkeys</span></header>
        <div className="meter">
          {L?.p05 != null && L?.p95 != null && <i className="band" style={{ left: `${pos(L.p05)}%`, width: `${pos(L.p95) - pos(L.p05)}%` }} />}
          {L?.best != null && <i className="tickm" style={{ left: `${pos(L.best)}%` }} title={`Best of ${nf(L.n)} monkeys ${pct(L.best)}`} />}
          {best && <i className="agent" style={{ left: `${pos(best.ret)}%`, background: colorOf(best) }} title={`${best.name} ${pct(best.ret)}`} />}
        </div>
        <div className="row3">
          <div><div className="lbl">Best agent</div><div className={"num " + tone(best?.ret)}>{best ? pct(best.ret) : "—"}</div></div>
          <div><div className="lbl">Best monkey</div><div className={"num " + tone(L?.best)}>{pct(L?.best)}</div></div>
          <div><div className="lbl">Beyond luck</div><div className="num">{M.lucky ?? "—"}<span className="mute"> / {M.agents.length}</span></div></div>
        </div>
      </section>

      <section className="w glass">
        <header><span className="lbl">Last night</span><span className="lbl faint">filled at the open</span></header>
        <div className="row3">
          <div><div className="lbl">Buys</div><div className="num up">{d?.buys ?? 0}</div></div>
          <div><div className="lbl">Sells</div><div className="num down">{d?.sells ?? 0}</div></div>
          <div><div className="lbl">Agents trading</div><div className="num">{traded}</div></div>
        </div>
        <div className="row3">
          <div><div className="lbl">Orders for next open</div><div className="num">{d?.orders ?? 0}</div></div>
          <div title="Companies set aside tonight because their data failed a check"><div className="lbl">Set aside</div><div className="num">{d?.excluded ?? 0}</div></div>
          <div><div className="lbl">Day</div><div className="num">{i}</div></div>
        </div>
      </section>

      <section className="w glass">
        <header><span className="lbl">Movers today</span></header>
        {i > 0 ? [...daily.slice(0, 2), ...daily.slice(-2).reverse()].map(({ p, ch }) => (
          <button key={p.id} className="line" onClick={() => onPick(p.id)}>
            <Shape p={p} /><span>{label(p)}</span><span className="faint num">{eur(M.valueAt(p, i))}</span><span className={"num " + tone(ch)}>{pct(ch, 2)}</span>
          </button>
        )) : <div className="mute">No moves yet</div>}
      </section>

      <section className="w glass" title="Evolution starts after the trial: the weakest are removed and the strongest have offspring.">
        <header><span className="lbl">Evolution</span><span className="lbl faint">generation 1</span></header>
        <div className="row3">
          <div><div className="lbl">Alive</div><div className="num">{M.agents.length}</div></div>
          <div><div className="lbl">Births</div><div className="num">0</div></div>
          <div><div className="lbl">Deaths</div><div className="num">0</div></div>
        </div>
      </section>
    </div>
  );
}
