// Ask v2 tools: typed, read-only questions to our own data. Each tool returns
//   lead     one plain sentence (also the no-AI answer when the free allowance is used up)
//   facts    short plain lines the model may use (every number it says must come from here)
//   visuals  card visuals built from the data (the model only picks one by key)
//   sources  citation chips (label + where it leads); show: "Show me" buttons; follow: next questions
import { CAPITAL, CAUSE_PLAIN, SIGNAL_PLAIN, companyName, companySector, dayName, dayShort, eur, pct, pts, tone } from "./store.js";
import { UNIVERSE } from "./universe.js";
import { RULES } from "./rules.js";

const r1 = x => Math.round(x * 10000) / 100;          // ratio -> percent with 2 decimals (for visuals)
const res = (o) => ({ facts: [], visuals: {}, sources: {}, show: {}, follow: [], ...o });
const SP_PLAIN = {
  arrow: "Trend followers: they buy shares that have been rising",
  wave: "Bargain hunters: they buy shares that just fell, hoping for a bounce",
  rock: "Calm and cheap: they buy steady companies and trade little",
  echo: "Meant to react to the news (news signals are still being tested, so today they use price signals)",
  plumb: "A bit of everything, with low risk",
};
const lostOrMade = (x) => x >= 0 ? `made ${eur(x)}` : `lost ${eur(-x).replace("EUR ", "EUR ")}`;
const agentChip = (p, label) => ({ label: label || `${p.name} card`, kind: p.type === "agent" ? "agent" : p.type === "monkey" ? "agent" : "ranking", go: { agent: p.id, view: "story" } });
const dayChip = (d, label) => ({ label: label || `Journal ${dayShort(d)}`, kind: "day", go: { date: d, view: "journal" }, d });
const marketLine = (C) => ({ name: "Just buying the market (S&P 500)", market: true, points: C.idx.series.map(([d, v]) => [d, r1(v / C.idx.start - 1)]) });
const lineOf = (p) => ({ name: p.name, id: p.id, species: p.sp || undefined, points: p.series.map(([d, v]) => [d, r1(v / p.start - 1)]) });

export function standingLine(C, p) {
  return `${p.name}: ${eur(p.v)} (${pct(p.retD)} since ${p.from === C.dates[0] ? "the start" : "its birth"}; ${p.vsD >= 0 ? "better" : "worse"} than just buying the market by ${Math.abs(p.vsD * 100).toFixed(2)} points)`;
}

// ---------- ranking / who is winning ----------
export function ranking(C) {
  const { ranked, idx, day, dates } = C;
  if (day === dates[0] || ranked.every(p => Math.abs(p.retD) < 1e-9))
    return res({ lead: `Nobody is ahead yet: on ${dayName(day)} every agent still has its ${eur(CAPITAL)}; the first trades happen at the next market open.`,
      facts: [`${dayName(day)} is day zero (the start). All ${ranked.length} agents have ${eur(CAPITAL)} each; first trades at the next open (${dayName(dates[1] || day)}).`],
      sources: { s: { label: "Ranking", kind: "ranking", go: { view: "race", date: day } } }, follow: ["How do the agents decide what to buy?", "What is a monkey here?"] });
  const beat = ranked.filter(p => p.vsD > 0), allLost = ranked.every(p => p.retD < 0);
  const lead = ranked[0], last = ranked[ranked.length - 1];
  const bestMonkey = [...C.monkeys].sort((a, b) => b.retD - a.retD)[0];
  const facts = [
    `As of ${dayName(day)} (${C.di} trading day${C.di === 1 ? "" : "s"} since the start on ${dayName(dates[0])}). Ranking = result compared with just buying the market (S&P 500 with dividends, in euros), because the risk-adjusted score needs more history.`,
    `Just buying the market (S&P 500 in euros): ${eur(idx.v)}, ${pct(idx.retD)}.`,
    `Leader: ${standingLine(C, lead)}.`,
    `Last: ${standingLine(C, last)}.`,
    `${beat.length} of ${ranked.length} agents are doing better than the market${beat.length ? ": " + beat.map(p => `${p.name} ${pts(p.vsD)}`).join(", ") : ""}.`,
    allLost ? `No agent is making money: all ${ranked.length} are below their starting ${eur(CAPITAL)}.` : `${ranked.filter(p => p.retD > 0).length} agents are above their starting money.`,
    `Full order: ` + ranked.map(p => `${p.rank}. ${p.name} ${pct(p.retD)} (vs market ${pts(p.vsD)})`).join("; ") + ".",
    bestMonkey ? `Best of the 10 random 'monkeys' in the arena: ${bestMonkey.name} ${pct(bestMonkey.retD)}${bestMonkey.retD > lead.retD ? ", better than every agent" : ""}.` : "",
    `Equal-weight benchmark (all 101 companies, equal amounts): ${pct(C.eq?.retD)}.`,
  ].filter(Boolean);
  return res({
    lead: `${lead.name} is ahead: ${lead.retD < 0 ? `it is down ${pct(-lead.retD).slice(1)}` : `it is up ${pct(lead.retD).slice(1)}`}, while just buying the market is ${idx.retD < 0 ? "down" : "up"} ${pct(Math.abs(idx.retD)).slice(1)}. ${beat.length} of ${ranked.length} agents are doing better than the market.`,
    facts, focus: { agent: lead.id },
    visuals: { bars: { type: "bars", unit: "%", items: [...ranked.map(p => ({ name: p.name, id: p.id, value: r1(p.retD), tone: tone(p.vsD), species: p.sp })), { name: "Market (S&P 500)", value: r1(idx.retD), tone: "flat", mark: "market" }].sort((a, b) => b.value - a.value) },
      line: { type: "line", unit: "%", series: [marketLine(C), lineOf(lead), lineOf(last)] } },
    sources: { rank: { label: `Ranking ${dayShort(day)}`, kind: "ranking", go: { view: "race", date: day } }, lead: agentChip(lead), last: agentChip(last) },
    show: { race: { label: "Show the race", go: { view: "race", date: day } }, lead: { label: `Show ${lead.name}`, go: { agent: lead.id, view: "story" } } },
    follow: [`Why is ${lead.name} ahead?`, `Is ${lead.name} better than luck?`, `Why is ${last.name} last?`],
  });
}

// ---------- one agent ----------
const holdLine = h => `${companyName(h.t)} (${h.t}) ${(h.w * 100).toFixed(1)}% of the money, ${pct(h.gain, 1)} since bought on ${dayShort(h.since)}`;
function dnaPlain(p) {
  if (!p.dna) return null;
  const w = Object.entries(p.dna.w).filter(([, v]) => v).sort((a, b) => b[1] - a[1]);
  const d = p.dna;
  return `DNA (what it looks for): ` + w.map(([k, v]) => `${SIGNAL_PLAIN[k]?.[2] || k} ${v}%`).join(", ")
    + `; news weight ${p.dna.w.news || 0}%. Keeps ${d.picks} shares, at most ${Math.round(d.maxW * 100)}% each; reviews every ${d.review} trading days; holds at least ${d.minHold ?? "n/a"} days`
    + `; stop loss ${d.stop ? Math.round(d.stop * 100) + "%" : "none"}; safety brake ${d.brake ? `on (when the market is below its 200-day average it keeps only ${Math.round((1 - d.brake) * 100)}% invested)` : "none"}.`;
}
export function decisionPlain(p, l, pending = false) {
  const r = l.r || {};
  const who = companyName(l.t);
  const verb = pending ? (l.k === "buy" ? "will buy" : l.all ? "will sell all its" : "will sell part of its") : (l.k === "buy" ? "bought" : "sold");
  const drivers = (r.drivers || []).slice(0, 3).map(x => {
    const pl = SIGNAL_PLAIN[x.s]; return pl ? `${x.z >= 0 ? pl[0] : pl[1]} (${pl[2]} reading ${x.z >= 0 ? "+" : ""}${x.z.toFixed(2)} x weight ${x.w}% = ${x.term >= 0 ? "+" : ""}${x.term.toFixed(2)})` : x.s;
  });
  const when = pending ? `at the next market open (decided the night of ${dayName(l.dd)})` : `${l.eur ? "for " + eur(l.eur) + " " : ""}at the open of ${dayName(l.d)} (decided the night of ${dayName(l.dd)})`;
  return `${p.name} ${verb} ${who} (${l.t}) ${when}. Reason: ${CAUSE_PLAIN[r.cause] || r.cause || "n/a"}`
    + (/stop loss|limit/i.test(l.why || "") && r.cause === "stop_loss" ? ` (${((l.why || "").match(/Stop loss: ([^)]*\))/) || [, ""])[1].replace(/−/g, "-")})` : "")
    + (/Brake on/.test(l.why || "") ? "; brake on: the market is below its 200-day average, so it keeps only part of its money invested" + ((l.why || "").match(/only (\d+)%/) ? ` (${(l.why || "").match(/only (\d+)%/)[1]}%)` : "") : "")
    + (/Trims to the ([\d.]+)% target/.test(l.why || "") ? `; trims to ${(l.why || "").match(/Trims to the ([\d.]+)%/)[1]}% of its money` : "")
    + `. Score ${r.score != null ? r.score.toFixed(2) : "n/a"}${r.rank ? `, ${ordinal(r.rank)} of ${r.of} companies` : ""}. Main reasons: ${drivers.join("; ") || "n/a"}.`;
}
const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");

export function getAgent(C, id) {
  const p = C.byId[id];
  if (!p) return null;
  const hold = C.latest ? p.hold : [];
  const sorted = [...hold].sort((a, b) => b.gain - a.gain);
  const logs = p.log.filter(l => (l.k === "buy" || l.k === "sell") && l.d <= C.day);
  const pend = C.latest ? (p.next || []) : [];
  const luck = C.A.luck;
  const facts = [
    `${p.name}: ${p.type === "agent" ? `agent of the ${C.A.species[p.sp]?.label || p.sp} species. ${SP_PLAIN[p.sp] || ""}` : p.type === "monkey" ? "a random 'monkey': same rules and costs, picks at random" : p.type === "index" ? "the benchmark: just buying the S&P 500 (with dividends, in euros)" : "benchmark: all 101 companies in equal amounts"}. Born ${dayName(p.born || p.from)}${p.parents ? `, child of ${p.parents.join(" and ")}` : ""}.`,
    `As of ${dayName(C.day)}: ${eur(p.v)} (started with ${eur(p.start)}), ${pct(p.retD)}, so it has ${lostOrMade(p.v - p.start)}. Just buying the market over the same days: ${pct(p.idxD)}. Difference: ${pts(p.vsD)} (${p.vsD >= 0 ? "better" : "worse"} than the market).`,
    p.type === "agent" && p.rank ? `Rank ${p.rank} of ${C.ranked.length} agents (by result versus the market).` : "",
    `Day by day value: ` + p.series.map(([d, v]) => `${dayShort(d)} ${eur(v)}`).join(", ") + ". Daily change: " + p.series.slice(1).map(([d, v], i) => `${dayShort(d)} ${pct(v / p.series[i][1] - 1)}`).join(", ") + ".",
    `Worst drop from a peak so far: ${pct(-(p.mdd || 0))}. Fees paid: ${eur(p.fees)}. Dividends: ${eur(p.divs || 0)}. Cash: ${eur(p.cash)}.`,
    dnaPlain(p),
    hold.length ? `Holds ${hold.length} companies: ` + sorted.map(holdLine).join("; ") + "." : (C.latest ? "Holds no shares." : `Holdings on that day: ${Object.keys((p.positions || {})).join(", ") || "see the card"}.`),
    sorted.length ? `Best holding: ${companyName(sorted[0].t)} ${pct(sorted[0].gain, 1)}; worst: ${companyName(sorted[sorted.length - 1].t)} ${pct(sorted[sorted.length - 1].gain, 1)}.` : "",
    logs.length ? `Trades: ${logs.length}, all ${new Set(logs.map(l => l.d)).size === 1 ? "on " + dayName(logs[0].d) : "between " + dayName(logs[0].d) + " and " + dayName(logs[logs.length - 1].d)}. Last trade ${dayName(logs[logs.length - 1].d)}.` : "No trades yet.",
    ...logs.slice(-3).map(l => decisionPlain(p, l)),
    pend.length ? `Orders waiting for the next open: ` + pend.map(l => decisionPlain(p, l, true)).join(" ") : (C.latest ? "No orders waiting for the next open." : ""),
    p.pctAll != null && C.latest ? `Luck test: beats ${(p.pctAll * 100).toFixed(1)}% of 1,000 random monkeys with the same number of trades; the luck band (90% of monkeys) runs from ${pct(luck.p05)} to ${pct(luck.p95)}, so ${p.name} is ${p.retD > luck.p95 ? "ABOVE the luck band" : p.retD < luck.p05 ? "below the luck band" : "inside the luck band (could be luck)"}.` : "",
    p.type === "agent" ? `Badge: ${p.merit ? "merit" : "provisional"} (merit needs 12 months of life and passing the luck tests).` : "",
    p.dead ? `In the graveyard since ${p.dead.died}.` : "",
  ].filter(Boolean);
  const visuals = {
    stat: { type: "stat", value: Math.round(p.v), unit: "EUR", label: `${p.name} now`, sub: `${pct(p.retD)} · market ${pct(p.idxD)}`, tone: tone(p.retD) },
    line: { type: "line", unit: "%", series: [marketLine(C), lineOf(p)] },
  };
  if (hold.length) visuals.tiles = { type: "tiles", items: hold.map(h => ({ name: companyName(h.t), ticker: h.t, weight: Math.round(h.w * 1000) / 10, gain: Math.round(h.gain * 1000) / 10 })) };
  if (p.dna) visuals.dna = { type: "bars", unit: "%", items: Object.entries(p.dna.w).filter(([, v]) => v).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ name: SIGNAL_PLAIN[k]?.[2] || k, value: v, tone: "flat" })) };
  if (logs.length) visuals.decisions = { type: "list", items: logs.slice(-6).reverse().map(l => ({ d: l.d, text: `${l.k === "buy" ? "Bought" : "Sold"} ${companyName(l.t)}`, go: { agent: p.id, date: l.d, view: "detail" } })) };
  const sources = { card: agentChip(p) };
  if (logs.length) sources.dec = { label: `${p.name} · decisions ${dayShort(logs[logs.length - 1].d)}`, kind: "decision", go: { agent: p.id, date: logs[logs.length - 1].d, view: "detail" }, d: logs[logs.length - 1].d };
  if (p.pctAll != null && C.latest) sources.luck = { label: `${p.name} · luck test`, kind: "luck", go: { agent: p.id, view: "evidence" } };
  return res({
    lead: `${p.name} has ${eur(p.v)}: ${pct(p.retD)} since ${p.from === C.dates[0] ? "the start" : "its birth"}, ${p.vsD >= 0 ? "better" : "worse"} than just buying the market (${pct(p.idxD)}).`,
    facts, visuals, sources, focus: { agent: p.id },
    show: { story: { label: `Show ${p.name}`, go: { agent: p.id, view: "story" } }, hold: { label: `Show ${p.name}'s holdings`, go: { agent: p.id, view: "detail" } }, ev: { label: "Can I trust this?", go: { agent: p.id, view: "evidence" } } },
    follow: [`Why did ${p.name} buy ${sorted[0] ? companyName(sorted[0].t) : "its shares"}?`, `Is ${p.name} better than luck?`, `Compare ${p.name} with the leader`],
  });
}

// ---------- one decision ----------
export function explainDecision(C, id, ticker, date) {
  const p = C.byId[id]; if (!p) return null;
  let L = p.log.filter(l => (l.k === "buy" || l.k === "sell") && l.d <= C.day).map(l => ({ l, pending: false }));
  if (C.latest) L = L.concat((p.next || []).map(l => ({ l, pending: true })));
  if (ticker) L = L.filter(x => x.l.t === ticker);
  if (date) L = L.filter(x => x.l.d === date || x.l.dd === date);
  if (!L.length) return res({ lead: `${p.name} has no ${ticker ? companyName(ticker) + " " : ""}trade ${date ? "on " + dayName(date) : "in the archive"}.`, facts: [`No matching trade by ${p.name}${ticker ? " in " + companyName(ticker) : ""}${date ? " on " + dayName(date) : ""}.`], sources: { card: agentChip(p) } });
  const pick = L.slice(-4);
  const top = pick[pick.length - 1];
  const r = top.l.r || {};
  const facts = pick.map(x => decisionPlain(p, x.l, x.pending));
  const h = (C.latest ? p.hold : []).find(h => h.t === top.l.t);
  if (h) facts.push(`${p.name} still holds ${companyName(h.t)}: ${(h.w * 100).toFixed(1)}% of its money, ${pct(h.gain, 1)} since ${dayName(h.since)}.`);
  if (p.dna) facts.push(dnaPlain(p));
  const d = top.l.d || top.l.dd;
  return res({
    lead: `${p.name} ${top.pending ? "will " + (top.l.k === "buy" ? "buy" : "sell") : top.l.k === "buy" ? "bought" : "sold"} ${companyName(top.l.t)} because of ${CAUSE_PLAIN[r.cause] || "its rules"}.`,
    facts, focus: { agent: p.id, company: top.l.t, date: d },
    visuals: { drivers: { type: "drivers", items: (r.drivers || []).map(x => ({ label: `${(x.z >= 0 ? SIGNAL_PLAIN[x.s]?.[0] : SIGNAL_PLAIN[x.s]?.[1]) || x.s}`, push: x.term })), total: r.score != null ? { label: `Score (${ordinal(r.rank)} of ${r.of})`, value: r.score } : undefined } },
    sources: { dec: { label: `${p.name} · ${top.l.k} ${companyName(top.l.t)} ${top.pending ? "(next open)" : dayShort(top.l.d)}`, kind: "decision", go: { agent: p.id, date: top.pending ? C.day : top.l.d, view: "evidence", company: top.l.t }, d } },
    show: { why: { label: "Show the why", go: { agent: p.id, date: top.pending ? C.day : top.l.d, view: "evidence", company: top.l.t } } },
    follow: [`How is ${companyName(top.l.t)} doing since?`, `What else does ${p.name} own?`, `Who else owns ${companyName(top.l.t)}?`],
  });
}

// ---------- compare ----------
export function compareAgents(C, ids) {
  const ps = ids.map(i => C.byId[i]).filter(Boolean).slice(0, 5);
  if (ps.length < 2) return null;
  const facts = ps.map(p => `${standingLine(C, p)}; worst drop ${pct(-(p.mdd || 0))}; ${p.dna ? `reviews every ${p.dna.review} days, keeps ${p.dna.picks} shares` : p.type}${p.rank ? `; rank ${p.rank} of ${C.ranked.length}` : ""}.`);
  ps.filter(p => p.dna).forEach(p => facts.push(`${p.name} ${dnaPlain(p)}`));
  if (C.latest) {
    const sets = ps.map(p => new Set(p.hold.map(h => h.t)));
    const common = [...sets[0]].filter(t => sets.every(s => s.has(t)));
    facts.push(common.length ? `Owned by all of them: ${common.map(companyName).join(", ")}.` : "They own no company in common.");
  }
  const best = [...ps].sort((a, b) => b.retD - a.retD)[0];
  return res({
    lead: `${best.name} is doing better: ` + ps.map(p => `${p.name} ${pct(p.retD)}`).join(" vs ") + `, against ${pct(C.idx.retD)} for just buying the market.`,
    facts, focus: { agent: ps[0].id },
    visuals: { bars: { type: "bars", unit: "%", items: [...ps.map(p => ({ name: p.name, id: p.id, value: r1(p.retD), tone: tone(p.vsD), species: p.sp })), { name: "Market (S&P 500)", value: r1(C.idx.retD), tone: "flat", mark: "market" }] },
      line: { type: "line", unit: "%", series: [marketLine(C), ...ps.map(lineOf)] } },
    sources: Object.fromEntries(ps.map((p, i) => ["a" + i, agentChip(p)])),
    show: Object.fromEntries(ps.map((p, i) => ["a" + i, { label: `Show ${p.name}`, go: { agent: p.id, view: "story" } }])),
    follow: [`Why is ${best.name} ahead?`, `What do they both own?`, `Are they better than luck?`],
  });
}

// ---------- species ----------
export function speciesSummary(C) {
  const g = {};
  for (const p of C.agents) (g[p.sp] ||= []).push(p);
  const rows = Object.entries(g).map(([sp, ps]) => ({ sp, label: C.A.species[sp]?.label || sp, avg: ps.reduce((a, p) => a + p.retD, 0) / ps.length, best: [...ps].sort((a, b) => b.retD - a.retD)[0], n: ps.length })).sort((a, b) => b.avg - a.avg);
  return res({
    lead: `The ${rows[0].label} agents are doing best on average (${pct(rows[0].avg)}); the ${rows[rows.length - 1].label} agents worst (${pct(rows[rows.length - 1].avg)}). Just buying the market: ${pct(C.idx.retD)}.`,
    facts: rows.map(r => `${r.label} species (${SP_PLAIN[r.sp] || C.A.species[r.sp]?.about}): average ${pct(r.avg)} over ${r.n} agents; best ${r.best.name} ${pct(r.best.retD)}.`).concat([`Just buying the market: ${pct(C.idx.retD)}.`]),
    visuals: { bars: { type: "bars", unit: "%", items: [...rows.map(r => ({ name: r.label, value: r1(r.avg), tone: tone(r.avg - C.idx.retD), species: r.sp })), { name: "Market (S&P 500)", value: r1(C.idx.retD), tone: "flat", mark: "market" }] } },
    sources: { rank: { label: `Ranking ${dayShort(C.day)}`, kind: "ranking", go: { view: "race", date: C.day } } },
    show: { race: { label: "Show the race", go: { view: "race", date: C.day } } },
    follow: [`Why are the ${rows[0].label} agents ahead?`, `Why are the ${rows[rows.length - 1].label} agents behind?`, "What does each species look for?"],
  });
}

// ---------- market ----------
export async function marketSummary(C, dates) {
  const ds = (dates && dates.length ? dates : [C.day]).filter(d => C.dates.includes(d) && d <= C.day);
  if (!ds.length) return null;
  const facts = [], sources = {}, visuals = {};
  let usd = 1, fx0 = null, fx1 = null, world = null;
  for (const d of ds) {
    const j = await C.store.journal(d); if (!j) continue;
    const m = j.markets;
    if (m.spx != null) usd *= 1 + m.spx;
    const prev = C.dates[C.dates.indexOf(d) - 1];
    if (fx0 == null) { const pj = prev ? await C.store.journal(prev) : null; fx0 = pj?.markets?.eurusd ?? m.eurusd; }
    fx1 = m.eurusd;
    const mv = [...(m.movers || [])].sort((a, b) => b.ret - a.ret);
    facts.push(`${dayName(d)}: S&P 500 ${m.spx == null ? "no change (day zero)" : pct(m.spx)} in dollars; ${m.above_ma ? "above" : "below"} its 200-day average; 1 euro = ${m.eurusd} dollars.`
      + (m.sectors?.length ? ` Best sector ${m.sectors[0].sector} ${pct(m.sectors[0].ret)}, worst ${m.sectors[m.sectors.length - 1].sector} ${pct(m.sectors[m.sectors.length - 1].ret)}.` : "")
      + (mv.length ? ` Biggest risers: ${mv.slice(0, 3).map(x => `${companyName(x.t)} ${pct(x.ret, 1)}`).join(", ")}. Biggest fallers: ${mv.slice(-3).reverse().map(x => `${companyName(x.t)} ${pct(x.ret, 1)}`).join(", ")}.` : "")
      + ` Arena: ${j.arena.fills ? `${j.arena.buys} buys and ${j.arena.sells} sells` : "no trades by the agents"} at the open` + (j.arena.best?.length ? `; best agent of the day ${j.arena.best[0].name} ${pct(j.arena.best[0].ret)}, worst ${j.arena.worst[0].name} ${pct(j.arena.worst[0].ret)}` : "") + ".");
    if (C.latest && mv.length) {
      const own = t => C.agents.filter(p => p.hold.some(h => h.t === t)).map(p => p.name);
      facts.push(`Who owns the day's biggest movers: ` + [...mv.slice(-3).reverse(), ...mv.slice(0, 2)].map(x => `${companyName(x.t)} (${pct(x.ret, 1)}): ${own(x.t).length ? own(x.t).join(", ") : "no agent"}`).join("; ") + ".");
    }
    if (j.world?.headline) { world = j.world; facts.push(`World brief of ${dayName(d)} (written overnight by our own AI reader from the news; it does not prove causes): "${j.world.headline}". ` + (j.world.items || []).slice(0, 3).map(it => `${it.topic}: ${it.summary}`).join(" ")); }
    sources["d" + d] = dayChip(d);
    (j.world?.items || []).slice(0, 2).forEach((it, k) => { const c = (it.cites || [])[0]; if (c?.url) sources[`n${d}${k}`] = { label: c.title?.slice(0, 60) || it.topic, kind: "news", url: c.url, d, go: { date: d, view: "journal" } }; });
  }
  if (ds.length > 1) {
    const i0 = C.dates.indexOf(ds[0]) - 1;
    const eurIdx = C.idx.series.find(x => x[0] === ds[ds.length - 1])?.[1] / (C.idx.series[Math.max(0, i0)]?.[1] || C.idx.start) - 1;
    facts.push(`Over ${dayName(ds[0])} to ${dayName(ds[ds.length - 1])}: S&P 500 ${pct(usd - 1)} in dollars (days compounded); in euros with dividends and costs ${pct(eurIdx)}. 1 euro bought ${fx0} dollars before and ${fx1} after: ${fx1 < fx0 ? "the dollar got stronger, which softened the fall for a euro investor" : fx1 > fx0 ? "the dollar got weaker, which made the fall bigger for a euro investor" : "no change"}.`);
  }
  facts.push(`Since the start (${dayName(C.dates[0])}): just buying the market in euros ${pct(C.idx.retD)} (${eur(C.idx.v)} from ${eur(CAPITAL)}).`);
  visuals.line = { type: "line", unit: "%", series: [marketLine(C)] };
  const last = await C.store.journal(ds[ds.length - 1]);
  if (last?.markets?.sectors?.length) visuals.sectors = { type: "bars", unit: "%", items: last.markets.sectors.map(s => ({ name: s.sector, value: r1(s.ret), tone: tone(s.ret) })) };
  if (last?.markets?.movers?.length) visuals.movers = { type: "bars", unit: "%", items: [...last.markets.movers].sort((a, b) => b.ret - a.ret).map(x => ({ name: companyName(x.t), value: r1(x.ret), tone: tone(x.ret) })) };
  const d = ds[ds.length - 1], jm = last?.markets;
  return res({
    lead: ds.length > 1 ? `From ${dayName(ds[0])} to ${dayName(d)} the S&P 500 moved ${pct(usd - 1)} in dollars.` : `On ${dayName(d)} the S&P 500 moved ${jm?.spx == null ? "0%" : pct(jm.spx)} (in dollars).`,
    facts, visuals, sources, focus: { date: d },
    show: { j: { label: `Open the journal of ${dayShort(d)}`, go: { date: d, view: "journal" } }, w: { label: "Show the world that day", go: { date: d, view: "world" } } },
    follow: [`Which agents did best on ${dayShort(d)}?`, `Why did ${jm?.movers?.length ? companyName([...jm.movers].sort((a, b) => a.ret - b.ret)[0].t) : "the market"} move?`, "How are the agents doing overall?"],
  });
}

// ---------- company ----------
export async function companyStory(C, t) {
  if (!UNIVERSE.find(r => r[0] === t)) return null;
  const name = companyName(t);
  const holders = C.latest ? C.P.filter(p => p.hold.some(h => h.t === t)) : [];
  const ag = holders.filter(p => p.type === "agent"), others = holders.filter(p => p.type !== "agent");
  const facts = [`${name} (${t}), sector ${companySector(t)}, one of the 101 companies (S&P 100) the agents can buy.`];
  facts.push(ag.length ? `Owned by ${ag.length} of ${C.agents.length} agents: ` + ag.map(p => { const h = p.hold.find(x => x.t === t); return `${p.name} (${(h.w * 100).toFixed(1)}% of its money, ${pct(h.gain, 1)} since ${dayShort(h.since)})`; }).join("; ") + "."
    : `No agent owns ${name}.` + (others.length ? ` Held by: ${others.map(p => p.name).join(", ")}.` : ""));
  if (ag.length && others.length) facts.push(`Also held by: ${others.map(p => p.name).join(", ")}.`);
  const moves = [];
  for (const d of C.dates.filter(d => d <= C.day)) {
    const j = await C.store.journal(d); const m = j?.markets?.movers?.find(x => x.t === t);
    if (m) moves.push(`${dayName(d)} ${pct(m.ret, 2)} (one of the day's biggest moves)`);
  }
  if (moves.length) facts.push(`Big daily moves: ${moves.join("; ")}.`); else facts.push(`${name} was not among the biggest daily movers.`);
  const trades = [];
  for (const p of C.agents) for (const l of p.log) if (l.t === t && (l.k === "buy" || l.k === "sell") && l.d <= C.day) trades.push(decisionPlain(p, l));
  if (C.latest) for (const p of C.agents) for (const l of p.next || []) if (l.t === t) trades.push(decisionPlain(p, l, true));
  facts.push(...trades.slice(0, 6)); if (trades.length > 6) facts.push(`(${trades.length - 6} more trades in ${name}.)`);
  const al = (await C.store.alerts())?.alerts?.filter(a => a.ticker === t) || [];
  if (al.length) facts.push(`Disclosed trades by insiders or politicians in ${name}: ${al.length}, e.g. ${al.slice(0, 2).map(a => `${a.kind === "congress" ? "a member of Congress" : `an insider (${a.role})`} ${a.action === "sell" ? "sold" : "bought"} on ${a.traded_on}, disclosed ${a.delay_days} days later${a.note ? " (" + a.note + ")" : ""}`).join("; ")}. Disclosures, not accusations.`);
  const docs = (await C.store.docs())?.docs || {};
  const key = name.split(/[ (]/)[0].toLowerCase();
  const news = Object.values(docs).filter(d => d.title && d.title.toLowerCase().includes(key) && (!d.published_at || d.published_at.slice(0, 10) <= C.day)).sort((a, b) => (b.published_at || "").localeCompare(a.published_at || "")).slice(0, 3);
  news.forEach(n => facts.push(`News (${(n.published_at || "").slice(0, 10)}, ${n.source}): "${n.title}".`));
  const sources = {};
  news.forEach((n, i) => { sources["n" + i] = { label: n.title.slice(0, 60), kind: "news", url: n.url, d: (n.published_at || "").slice(0, 10) }; });
  ag.slice(0, 2).forEach((p, i) => { sources["a" + i] = agentChip(p, `${p.name} · ${name}`); });
  if (!Object.keys(sources).length) sources.c = { label: `${name} in the journal`, kind: "company", go: { company: t, view: "journal", date: C.day } };
  return res({
    lead: ag.length ? `${name} is owned by ${ag.length} agent${ag.length > 1 ? "s" : ""}.` : `No agent owns ${name}.`,
    facts, sources, focus: { company: t },
    visuals: ag.length ? { holders: { type: "bars", unit: "%", items: ag.map(p => { const h = p.hold.find(x => x.t === t); return { name: p.name, id: p.id, value: Math.round(h.gain * 1000) / 10, tone: tone(h.gain), species: p.sp }; }) } } : {},
    show: { co: { label: `Show ${name}`, go: { company: t, view: "network" } } },
    follow: [`Why did agents buy ${name}?`, `How did ${name} move this week?`, `Any news about ${name}?`],
  });
}

// ---------- holdings across agents ----------
export function holdingsOverview(C) {
  if (!C.latest) return res({ lead: "Holdings are only detailed for the last night.", facts: ["Holdings across agents are available for the last night only."] });
  const cnt = {};
  for (const p of C.agents) for (const h of p.hold) (cnt[h.t] ||= []).push(p.name);
  const top = Object.entries(cnt).sort((a, b) => b[1].length - a[1].length);
  const fees = C.agents.reduce((a, p) => a + p.fees, 0);
  return res({
    lead: `${companyName(top[0][0])} is owned by the most agents (${top[0][1].length} of ${C.agents.length}).`,
    facts: [`Most-owned companies: ` + top.slice(0, 8).map(([t, n]) => `${companyName(t)} ${n.length} agents`).join(", ") + ".",
      `${top.length} different companies are owned by at least one agent.`,
      `Fees paid by the ${C.agents.length} agents so far: ${eur(fees)} in total (about ${eur(fees / C.agents.length)} each; costs are about EUR 20 per EUR 10,000 traded).`],
    visuals: { bars: { type: "bars", unit: "", items: top.slice(0, 10).map(([t, n]) => ({ name: companyName(t), value: n.length, tone: "flat" })) } },
    sources: { rank: { label: `Holdings ${dayShort(C.day)}`, kind: "company", go: { view: "network", date: C.day } } },
    follow: [`Who owns ${companyName(top[0][0])}?`, "Which company fell the most?", "Who is winning?"],
  });
}

// ---------- orders waiting for the next open ----------
export function pendingOrders(C) {
  if (!C.latest) return res({ lead: "Waiting orders are only known for the last night.", facts: ["Pending orders exist only for the last night."] });
  const rows = C.agents.filter(p => p.next?.length);
  const facts = rows.length ? rows.flatMap(p => p.next.map(l => decisionPlain(p, l, true))) : ["No agent has orders waiting for the next open."];
  facts.push(`Agents with a safety brake gene: ${C.agents.filter(p => p.dna?.brake).map(p => `${p.name} (keeps ${Math.round((1 - p.dna.brake) * 100)}% invested when the market is below its 200-day average; reviews every ${p.dna.review} days)`).join(", ") || "none"}. The S&P 500 is now ${C.A.day?.aboveMa200 === false ? "below" : "above"} its 200-day average; each brake agent acts at its next review.`);
  facts.push(`Agents with no waiting orders: ${C.agents.filter(p => !p.next?.length).length} of ${C.agents.length} (they act only at their own review day; reviews happen every few days, depending on each agent).`);
  return res({
    lead: rows.length ? `${rows.length} agent${rows.length > 1 ? "s have" : " has"} orders for the next market open: ${rows.map(p => p.name).join(", ")}.` : "No agent has orders for the next market open.",
    facts, sources: Object.fromEntries(rows.slice(0, 3).map((p, i) => ["p" + i, { label: `${p.name} · next open`, kind: "decision", go: { agent: p.id, view: "detail", date: C.day } }])),
    show: Object.fromEntries(rows.slice(0, 2).map((p, i) => ["p" + i, { label: `Show ${p.name}`, go: { agent: p.id, view: "detail" } }])),
    follow: rows.length ? [`Why is ${rows[0].name} selling?`, "What is the brake rule?", "What is a stop loss?"] : ["When do agents review their holdings?"],
  });
}

// ---------- luck ----------
export function luckTest(C, id) {
  const L = C.A.luck; if (!L) return null;
  const k = Math.min(C.di, L.s.length - 1), band = L.s[k];
  const p = id ? C.byId[id] : null;
  const above = C.agents.filter(a => C.latest && a.retD > L.p95);
  const monkeysBetter = C.monkeys.filter(m => m.retD > (C.ranked[0]?.retD ?? 0));
  const facts = [
    `The luck band is where 90% of 1,000 random 'monkeys' end up (they follow the same rules, trade as often and pay the same costs, but pick shares at random). It shows what luck alone can do.`,
    `On ${dayName(C.day)} the band runs from ${pct(band[0])} (5th percentile) to ${pct(band[1])} (95th percentile)${C.latest ? `; median monkey ${pct(L.median)}; best of the 1,000 monkeys ${pct(L.best)}` : ""}.`,
    `Band over time: ` + L.s.slice(1, k + 1).map((b, i) => `${dayShort(C.dates[i + 1])} ${pct(b[0], 1)} to ${pct(b[1], 1)}`).join("; ") + ".",
    C.latest ? `Agents above the band (better than 95% of monkeys): ${above.length ? above.map(a => `${a.name} (beats ${(a.pctAll * 100).toFixed(1)}%)`).join(", ") : "none"}.` : "",
    monkeysBetter.length ? `Arena monkeys doing better than the best agent: ${monkeysBetter.map(m => `${m.name} ${pct(m.retD)}`).join(", ")}.` : "",
    `After ${C.di} trading day${C.di === 1 ? "" : "s"}, results are mostly luck: being above the band is a hint, not proof. Proof (the merit badge) needs at least 12 months and passing luck-adjusted tests. This is a trial run: results are wiped at the official start (1 March 2027).`,
  ].filter(Boolean);
  if (p && p.pctAll != null) facts.unshift(`${p.name}: ${pct(p.retD)}, beats ${(p.pctAll * 100).toFixed(1)}% of the 1,000 monkeys; ${p.retD > L.p95 ? "above" : p.retD < L.p05 ? "below" : "inside"} the luck band.`);
  return res({
    lead: p ? `${p.name} beats ${(p.pctAll * 100).toFixed(0)}% of 1,000 random monkeys${p.retD > L.p95 ? ": above the luck band, but it is far too early to call it skill" : ": inside the luck band, so its result could be luck"}.`
      : `${above.length ? above.map(a => a.name).join(", ") + (above.length > 1 ? " are" : " is") + " above the luck band" : "No agent is above the luck band"}, but after ${C.di} days that can still be luck.`,
    facts, focus: p ? { agent: p.id } : undefined,
    visuals: { luck: { type: "luck", unit: "%", value: p ? r1(p.retD) : r1(C.ranked[0].retD), p5: r1(band[0]), p50: C.latest ? r1(L.median) : null, p95: r1(band[1]), label: p ? p.name : C.ranked[0].name } },
    sources: { luck: { label: "Luck test (1,000 monkeys)", kind: "luck", go: { view: "evidence", agent: p?.id || C.ranked[0]?.id } } },
    show: { luck: { label: "Show the luck zone", go: { view: "race", date: C.day } } },
    follow: ["What is a monkey here?", "When does an agent earn the merit badge?", "Did a monkey beat the agents?"],
  });
}

// ---------- rules and terms ----------
export function rules(C, topic) {
  const q = (topic || "").toLowerCase();
  const hits = RULES.filter(r => r.keys.some(k => q.includes(k)));
  const use = (hits.length ? hits : RULES.filter(r => r.id === "game")).slice(0, 3);
  return res({
    lead: use[0].text.split(". ")[0] + ".",
    facts: use.map(r => r.text), sources: Object.fromEntries(use.map(r => [r.id, { label: `Rules · ${r.title}`, kind: "rules", go: { view: r.view || "evidence" } }])),
    follow: use[0].follow || ["Who is winning?", "What is the luck band?", "How do agents decide what to buy?"],
  });
}

// ---------- evolution and merit ----------
export async function evolution(C) {
  const T = await C.store.tree(), M = await C.store.merit();
  const facts = [RULES.find(r => r.id === "evolution").text];
  if (T) facts.push(`Now: generation ${C.A.meta.generation || 1}; ${T.evaluations?.length || 0} selections so far; ${T.nodes?.filter(n => n.alive).length ?? C.agents.length} agents alive, ${T.nodes?.filter(n => !n.alive).length ?? 0} in the graveyard. ${T.evidence || ""}`);
  if (M) facts.push(`Merit badge: ${Object.values(M.agents || {}).filter(a => a.badge === "merit").length} agents have it; the others are provisional. Still missing for everyone: ${(Object.values(M.agents || {})[0]?.badge_missing || []).join(", ")}.`);
  return res({
    lead: "Every month, the 4 weakest agents with at least 3 months of life go to the graveyard and new ones are born from the best; the first real selection is on 1 June 2027.",
    facts, sources: { evo: { label: "Evolution rules", kind: "evolution", go: { view: "evolution" } }, ...(M ? { merit: { label: "Merit report", kind: "merit", go: { view: "evidence" } } } : {}) },
    show: { tree: { label: "Show the family tree", go: { view: "evolution" } } },
    follow: ["How is an agent born?", "What does the merit badge need?", "Who is losing the most?"],
  });
}

export async function lab(C) {
  const R = await C.store.lab(); if (!R) return null;
  const S = Object.entries(R.signals || {});
  const by = s => S.filter(([, v]) => v.status === s).length;
  return res({
    lead: `${S.length} new signals are being tested in the Signal Lab; ${by("admitted") || "none"} admitted so far.`,
    facts: [`Signals in the lab: ${S.map(([k, v]) => `${k.replace(/^intel\./, "").replace(/_/g, " ")} (${v.status}, ${v.observations ?? 0} observations)`).join("; ")}.`,
      `To be admitted into agents' DNA a signal needs at least ${R.gates?.min_observations} observations, a t-statistic above ${R.gates?.min_nw_t}, the same sign in ${R.gates?.min_same_sign_subperiods} of ${R.gates?.subperiods} sub-periods, and it must survive costs. ${R.note || ""}`,
      `Status counts: shadow ${by("shadow")}, passes the gates ${by("passes_gates")}, rejected ${by("rejected")}, admitted ${by("admitted")}.`],
    sources: { lab: { label: "Signal Lab report", kind: "lab", go: { view: "lab" } } },
    show: { lab: { label: "Show the lab", go: { view: "lab" } } },
    follow: ["Why do signals need 250 observations?", "Does any agent use news?", "What is a t-statistic?"],
  });
}

export async function people(C, t) {
  const A = await C.store.alerts(); if (!A) return null;
  const al = (A.alerts || []).filter(a => (!t || a.ticker === t) && String(a.disclosed_at).slice(0, 10) <= C.day);
  const owned = new Set(C.latest ? C.agents.flatMap(p => p.hold.map(h => h.t)) : []);
  const byT = {};
  al.forEach(a => (byT[a.ticker] ||= []).push(a));
  const rows = Object.entries(byT).sort((a, b) => b[1].length - a[1].length);
  return res({
    lead: `${al.length} trades by company insiders or politicians were disclosed${t ? " in " + companyName(t) : ""}; these are disclosures, not accusations.`,
    facts: [`Disclosed trades: ${al.filter(a => a.kind === "insider").length} by company insiders, ${al.filter(a => a.kind === "congress").length} by members of Congress. Always disclosed days after the trade.`,
      ...rows.slice(0, 6).map(([tk, xs]) => `${companyName(tk)}${owned.has(tk) ? " (owned by some agents)" : ""}: ${xs.length} disclosed ${xs.map(x => x.action).filter((v, i, a) => a.indexOf(v) === i).join("/")} trades, e.g. ${xs[0].kind === "congress" ? "a member of Congress" : `an insider (${xs[0].role})`} traded on ${xs[0].traded_on}, disclosed ${xs[0].delay_days} days later${xs[0].note ? ` (${xs[0].note})` : ""}.`),
      "A pattern worth noting, not an accusation; no agent uses these yet (the Mirror strategy is tested in the lab)."],
    sources: { ppl: { label: "People: disclosures", kind: "people", go: { view: "people", date: C.day } } },
    show: { ppl: { label: "Show the people", go: { view: "people" } } },
    follow: ["Does any agent copy insiders?", "What is a 10b5-1 plan?", "Who owns the companies with insider sales?"],
  });
}

export async function findNews(C, words, date) {
  const docs = (await C.store.docs())?.docs || {};
  const w = (words || []).map(x => x.toLowerCase()).filter(x => x.length > 2);
  const hits = Object.values(docs).filter(d => d.title && (!date || (d.published_at || "").slice(0, 10) <= date) && (!w.length || w.some(x => d.title.toLowerCase().includes(x))))
    .sort((a, b) => (b.published_at || "").localeCompare(a.published_at || "")).slice(0, 5);
  const d = date || C.day;
  const j = await C.store.journal(d);
  const facts = [];
  if (j?.world?.headline) facts.push(`World brief of ${dayName(d)} (our own AI reader, from the news): "${j.world.headline}". ` + (j.world.items || []).map(it => `${it.topic}: ${it.summary}`).join(" "));
  hits.forEach(n => facts.push(`News ${(n.published_at || "").slice(0, 10)} (${n.source}): "${n.title}".`));
  if (!facts.length) return null;
  const sources = { d: dayChip(d, `World brief ${dayShort(d)}`) };
  hits.slice(0, 3).forEach((n, i) => { sources["n" + i] = { label: n.title.slice(0, 60), kind: "news", url: n.url, d: (n.published_at || "").slice(0, 10) }; });
  return res({ lead: j?.world?.headline ? `The world brief of ${dayName(d)}: "${j.world.headline}".` : `Recent news: "${hits[0].title}".`, facts, sources, focus: { date: d },
    show: { w: { label: "Show the world", go: { view: "world", date: d } } }, follow: ["How did the market react?", "Which agents were hit?", "What happened the day before?"] });
}

// The catalogue the model sees (names and arguments only).
export const CATALOG = `ranking() | get_agent(agent) | explain_decision(agent, company?, date?) | compare_agents(agents[]) | species() | market_summary(dates[]) | company_story(company) | holdings_overview() | pending_orders() | luck_test(agent?) | rules(topic) | evolution() | lab() | people(company?) | find_news(words[], date?)`;

export async function runTool(C, name, a = {}) {
  const agent = x => { const s = String(x || "").toLowerCase().replace(/\s+/g, "-"); return C.byId[s] ? s : (C.P.find(p => p.name.toLowerCase() === String(x || "").toLowerCase())?.id || null); };
  const co = x => { const s = String(x || "").toUpperCase(); return UNIVERSE.find(r => r[0] === s)?.[0] || UNIVERSE.find(r => r[1].toLowerCase().startsWith(String(x || "").toLowerCase()))?.[0] || null; };
  switch (name) {
    case "ranking": return ranking(C);
    case "get_agent": return agent(a.agent) ? getAgent(C, agent(a.agent)) : null;
    case "explain_decision": return agent(a.agent) ? explainDecision(C, agent(a.agent), co(a.company), a.date || null) : null;
    case "compare_agents": return compareAgents(C, (a.agents || []).map(agent).filter(Boolean));
    case "species": return speciesSummary(C);
    case "market_summary": return marketSummary(C, a.dates || (a.date ? [a.date] : null));
    case "company_story": return co(a.company) ? companyStory(C, co(a.company)) : null;
    case "holdings_overview": return holdingsOverview(C);
    case "pending_orders": return pendingOrders(C);
    case "luck_test": return luckTest(C, agent(a.agent));
    case "rules": return rules(C, a.topic);
    case "evolution": return evolution(C);
    case "lab": return lab(C);
    case "people": return people(C, co(a.company));
    case "find_news": return findNews(C, a.words || [], a.date || null);
    default: return null;
  }
}
