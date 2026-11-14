import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { buildModel, loadArena, type Arena, type Model } from "./data";
import { detectTier, hasWebGL2, savedTier, saveTier, type Tier } from "./quality";
import { Board, Help, Kpis, Legend, Podium, Tip, Top, type TipState } from "./hud";
import { AgentCard } from "./card/AgentCard";
import { Flat } from "./scene/Flat";

const World = lazy(() => import("./scene/World"));

function report() {
  try {
    const m = (n: string) => Math.round((performance.getEntriesByName(n)[0] as PerformanceMark | undefined)?.startTime ?? -1);
    const r = { ui: m("arena:ui"), world: m("arena:3d"), flat: m("arena:2d") };
    (window as unknown as { ARENA_PERF: unknown }).ARENA_PERF = r;
    if (/[?&]perf\b/.test(location.search)) console.table(r);
  } catch { /* ignore */ }
}

export default function App() {
  const [A, setA] = useState<Arena | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { loadArena().then(setA).catch(e => setErr(String(e))); }, []);
  if (err) return <div className="boot">Data unavailable</div>;
  if (!A) return <div className="boot">Arena</div>;
  return <Ready A={A} />;
}

function Ready({ A }: { A: Arena }) {
  const M: Model = useMemo(() => buildModel(A), [A]);
  const gl = useMemo(hasWebGL2, []);
  const [tier, setTierState] = useState<Tier>(() => (gl ? savedTier() || detectTier() : "lite"));
  const setTier = useCallback((t: Tier) => { setTierState(t); saveTier(t); }, []);
  const [open, setOpen] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [tip, setTip] = useState<TipState>(null);
  const [help, setHelp] = useState(false);
  const [board, setBoard] = useState(false);

  useEffect(() => { performance.mark("arena:ui"); report(); }, []);

  // deep links: #/<participant>
  useEffect(() => {
    const route = () => { const m = location.hash.match(/^#\/(.+)$/); setOpen(m && M.byId[m[1]] ? m[1] : null); };
    route(); addEventListener("hashchange", route); return () => removeEventListener("hashchange", route);
  }, [M]);
  const show = useCallback((id: string | null) => {
    setTip(null); setBoard(false);
    history.replaceState(null, "", id ? "#/" + id : location.pathname + location.search);
    setOpen(id);
  }, []);
  const onHover = useCallback((id: string | null, x?: number, y?: number) => {
    setHover(id); setTip(id && x != null && y != null ? { id, x, y } : null);
  }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") { if (open) show(null); else setHelp(false); } };
    addEventListener("keydown", k); return () => removeEventListener("keydown", k);
  }, [open, show]);

  // the 2D view is the static first frame; it fades out once the 3D world has drawn
  const [worldUp, setWorldUp] = useState(false);
  const onReady = useCallback((what: "3d" | "2d") => {
    if (what === "3d") setTimeout(() => setWorldUp(true), 700);
    if (what === "2d" && performance.getEntriesByName("arena:2d").length) return;
    performance.mark("arena:" + what); report();
  }, []);
  useEffect(() => { if (tier === "lite") setWorldUp(false); }, [tier]);

  return (
    <>
      <div id="stage" aria-hidden="true">
        {(tier === "lite" || !worldUp) && <div className={tier === "lite" ? "" : "poster"}><Flat M={M} onPick={show} onHover={onHover} onReady={onReady} /></div>}
        {tier !== "lite" && <Suspense fallback={null}><World M={M} tier={tier} paused={!!open || help} hover={hover} onPick={show} onHover={onHover} onReady={onReady} onDegrade={() => setTierState(t => t === "ultra" ? "high" : t)} /></Suspense>}
        <div className="vignette" />
      </div>
      <div className="grain" />
      <main className="hud">
        <Top M={M} tier={tier} setTier={setTier} gl={gl} onHelp={() => setHelp(true)} />
        <Kpis M={M} onPick={show} />
        <Board M={M} open={board} hover={hover} onPick={show} onHover={id => setHover(id)} />
        <Podium M={M} onPick={show} />
        <Legend M={M} />
        <button className="rankbtn" onClick={() => setBoard(b => !b)}>Ranking</button>
        <footer className="fine">Simulated money · Not investment advice</footer>
      </main>
      <Tip M={M} tip={tip} />
      {open && M.byId[open] && <AgentCard M={M} p={M.byId[open]} onClose={() => show(null)} onGo={show} />}
      {help && <Help M={M} onClose={() => setHelp(false)} />}
    </>
  );
}
