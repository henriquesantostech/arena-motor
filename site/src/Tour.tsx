// A 20-second guided tour on the first visit (and on demand from Help or ⌘K): the camera sweeps around
// the arena while short captions point at the parts that matter. Skippable at any moment.
import { useEffect, useState } from "react";

const STEPS: { sel: string; title: string; text: string }[] = [
  { sel: "#stage", title: "The arena", text: "Every crystal is an agent trading simulated money on the S&P 100. Colour = species, size = money." },
  { sel: "#stage", title: "The water is the S&P 500", text: "Above the water = beating the index. The grey band is luck: where random monkeys end up." },
  { sel: ".kpis", title: "At a glance", text: "How many agents beat the index, and how many beat luck." },
  { sel: ".podium", title: "Podium", text: "Provisional until there is enough history. Tap any agent for its card, its DNA and every decision." },
  { sel: ".tm", title: "Time Machine", text: "Drag or press play to replay any night exactly as it was known then." },
  { sel: ".askbtn", title: "Ask", text: "Ask anything in any language, or say “show Rock-02 in December”. Answers cite the archive." },
];
const KEY = "arena.tour.v1";
export const tourSeen = () => { try { return localStorage.getItem(KEY) === "1"; } catch { return true; } };

export function Tour({ onEnd }: { onEnd: () => void }) {
  const [k, setK] = useState(0);
  const [box, setBox] = useState<DOMRect | null>(null);
  const end = () => { try { localStorage.setItem(KEY, "1"); } catch { /* private mode */ } onEnd(); };
  useEffect(() => {
    const el = document.querySelector(STEPS[k].sel);
    setBox(el && STEPS[k].sel !== "#stage" ? el.getBoundingClientRect() : null);
    const t = setTimeout(() => (k < STEPS.length - 1 ? setK(k + 1) : end()), 3400);
    return () => clearTimeout(t);
  }, [k]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") end(); if (e.key === "ArrowRight") setK(x => Math.min(x + 1, STEPS.length - 1)); };
    addEventListener("keydown", key); return () => removeEventListener("keydown", key);
  }); // eslint-disable-line react-hooks/exhaustive-deps
  const s = STEPS[k];
  return (
    <div className="tour" role="dialog" aria-live="polite" aria-label="Guided tour">
      {box && <div className="spot" style={{ left: box.left - 8, top: box.top - 8, width: box.width + 16, height: box.height + 16 }} />}
      <div className="tcap glass" style={box ? { left: Math.min(Math.max(16, box.left), innerWidth - 380), top: box.top > innerHeight / 2 ? box.top - 150 : box.bottom + 18 } : undefined}>
        <div className="lbl">{k + 1} / {STEPS.length}</div>
        <b>{s.title}</b>
        <span>{s.text}</span>
        <div className="tbar"><i key={k} /></div>
        <div className="tbtn"><button className="chip" onClick={end}>Skip</button><button className="chip on" onClick={() => (k < STEPS.length - 1 ? setK(k + 1) : end())}>{k < STEPS.length - 1 ? "Next" : "Done"}</button></div>
      </div>
    </div>
  );
}
