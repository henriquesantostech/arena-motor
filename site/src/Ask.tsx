// ASK panel: type or speak; the copilot answers from the archive (as known at the selected day), with
// citations, and can drive the interface ("show Arrow-03 in March"). Voice uses the browser's own speech
// recognition and voice, so audio is handled by the browser, never sent to our servers.
import { useEffect, useRef, useState } from "react";
import { dayY, type Model } from "./data";
import { ask, parseCommand, search, type Action, type Passage } from "./copilot";

type Msg = { who: "me" | "ai"; text: string; cites?: Passage[]; mode?: "ai" | "search" | "command"; asOf?: string; model?: string };
type SR = { lang: string; interimResults: boolean; continuous: boolean; start: () => void; stop: () => void; onresult: (e: { results: { 0: { transcript: string } }[] }) => void; onend: () => void; onerror: () => void };

const SUGGEST = ["Who is leading and why?", "Show Rock-02", "What happened on the first trading day?", "How does the luck band work?"];

export function Ask({ M, i, onAction, onClose }: { M: Model; i: number; onAction: (a: Action) => void; onClose: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(false);
  const recRef = useRef<SR | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const lang = navigator.language || "en";
  const asOf = M.A.meta.dates[i] || null;
  const SRC = (window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR }).SpeechRecognition
    || (window as unknown as { webkitSpeechRecognition?: new () => SR }).webkitSpeechRecognition;
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [msgs, busy]);
  useEffect(() => () => { recRef.current?.stop(); speechSynthesis?.cancel(); }, []);

  const valid = (a: Action) => a.type === "open" ? !!(a.id && M.byId[a.id]) : a.type === "date" ? !!(a.d && M.A.meta.dates.includes(a.d))
    : a.type === "lens" ? ["today", "arena", "evolution", "journal"].includes(a.lens || "") : a.type === "close";
  const say = (text: string) => {
    if (!speak || !("speechSynthesis" in window)) return;
    speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.lang = lang; speechSynthesis.speak(u);
  };

  async function submit(text: string) {
    const question = text.trim(); if (!question || busy) return;
    setQ(""); setMsgs(m => [...m, { who: "me", text: question }]); setBusy(true);
    try {
      const cmd = parseCommand(question, M).filter(valid);
      cmd.forEach(onAction);
      const isQuestion = /\?|^(who|what|why|how|when|where|which|is|are|does|did|can|explain|compare|quem|o que|porque|como|quando|qual)\b/i.test(question);
      if (cmd.length && !isQuestion) {
        const t = "Done: " + cmd.map(a => a.type === "open" ? M.byId[a.id!].name : a.type === "date" ? dayY(a.d) : a.type === "lens" ? a.lens : "closed").join(" · ");
        setMsgs(m => [...m, { who: "ai", text: t, mode: "command" }]); say(t); return;
      }
      const passages = await search(question, asOf, 10);
      const r = await ask(question, passages, asOf, lang);
      if ("error" in r) {
        const t = passages.length ? (r.error === "quota" ? "Today's free AI allowance is used up. Here is what the archive says:" : "The AI is unavailable right now. Here is what the archive says:")
          : "Nothing in the archive matches that.";
        setMsgs(m => [...m, { who: "ai", text: t, cites: passages.slice(0, 5), mode: "search", asOf: asOf || undefined }]);
        return;
      }
      const byId = new Map(passages.map(p => [p.id, p]));
      (r.actions || []).filter(valid).forEach(onAction);
      setMsgs(m => [...m, { who: "ai", text: r.text, cites: r.cite.map(id => byId.get(id)!).filter(Boolean), mode: "ai", asOf: asOf || undefined, model: (r as { model?: string }).model }]);
      say(r.text);
    } finally { setBusy(false); }
  }

  function mic() {
    if (!SRC) return;
    if (listening) { recRef.current?.stop(); return; }
    const rec = new SRC(); rec.lang = lang; rec.interimResults = false; rec.continuous = false;
    rec.onresult = e => { const t = e.results[0][0].transcript; setListening(false); submit(t); };
    rec.onend = () => setListening(false); rec.onerror = () => setListening(false);
    recRef.current = rec; setListening(true); rec.start();
  }

  const goto = (p: Passage) => {
    if (p.ref?.date) onAction({ type: "date", d: p.ref.date });
    if (p.ref?.lens) onAction({ type: "lens", lens: p.ref.lens });
    if (p.ref?.open) onAction({ type: "open", id: p.ref.open });
  };

  return (
    <aside className="ask glass" aria-label="Ask the copilot">
      <header>
        <span className="lbl"><span className="askdot" />ASK · as of {asOf ? dayY(asOf) : "—"}</span>
        <span className="tools">
          <button className={"chip" + (speak ? " on" : "")} onClick={() => { setSpeak(s => !s); speechSynthesis?.cancel(); }} title="Read answers aloud">{speak ? "voice on" : "voice off"}</button>
          <button className="round" aria-label="Close" onClick={onClose}>✕</button>
        </span>
      </header>
      <div className="askbody">
        {!msgs.length && <div className="asksug">
          <div className="mute small">Answers come only from the arena's own archive, as known on the selected day, with sources. Simulated money; never investment advice.</div>
          {SUGGEST.map(s => <button key={s} className="chip" onClick={() => submit(s)}>{s}</button>)}
        </div>}
        {msgs.map((m, k) => (
          <div key={k} className={"amsg " + m.who}>
            <div className="atext">{m.text}</div>
            {m.cites && m.cites.length > 0 && <div className="acites">
              {m.cites.map(c => <button key={c.id} className="cite" onClick={() => goto(c)} title={c.text}>{c.title}{c.d ? ` · ${c.d.slice(5)}` : ""}</button>)}
            </div>}
            {m.who === "ai" && m.mode && <div className="ameta">{m.mode === "ai" ? `grounded answer · ${m.cites?.length || 0} sources` : m.mode === "search" ? "search only" : "interface command"}{m.model ? " · " + m.model.split("/").pop() : ""}</div>}
          </div>
        ))}
        {busy && <div className="amsg ai"><div className="atext typing"><i /><i /><i /></div></div>}
        <div ref={endRef} />
      </div>
      <form className="askin" onSubmit={e => { e.preventDefault(); submit(q); }}>
        {SRC && <button type="button" className={"round mic" + (listening ? " on" : "")} onClick={mic} aria-label={listening ? "Stop listening" : "Speak"} title="Speak">{listening ? "■" : "🎙"}</button>}
        <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder={listening ? "Listening…" : "Ask or command: “show Arrow-03 in March”"} maxLength={600} />
        <button className="round" type="submit" aria-label="Send" disabled={busy || !q.trim()}>↑</button>
      </form>
    </aside>
  );
}
