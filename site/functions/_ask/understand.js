// Ask v2: understanding the question before any AI is used. Finds agents, companies, species and dates
// (in English, Portuguese and Spanish), resolves "it"/"them" from the conversation, spots advice requests,
// ambiguity and screen commands, and plans which tools to call first.
import { UNIVERSE } from "./universe.js";

const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
  janeiro: 1, fevereiro: 2, "março": 3, marco: 3, abril: 4, maio: 5, junho: 6, julho: 7, agosto: 8, setembro: 9, outubro: 10, novembro: 11, dezembro: 12,
  enero: 1, febrero: 2, marzo: 3, mayo: 5, junio: 6, julio: 7, septiembre: 9, octubre: 10, noviembre: 11, diciembre: 12 };
const ALIAS = { google: "GOOGL", alphabet: "GOOGL", facebook: "META", "j&j": "JNJ", "johnson & johnson": "JNJ", "johnson and johnson": "JNJ",
  coke: "KO", "coca-cola": "KO", "coca cola": "KO", "p&g": "PG", "procter": "PG", berkshire: "BRK.B", "jp morgan": "JPM", jpmorgan: "JPM",
  exxon: "XOM", disney: "DIS", lilly: "LLY", "mcdonald": "MCD", "lowe's": "LOW", lowes: "LOW", "at&t": "T", "home depot": "HD", "3m": "MMM",
  pepsi: "PEP", unitedhealth: "UNH", "united health": "UNH", "general motors": "GM", "palo alto": "PANW", "bank of america": "BAC",
  "goldman": "GS", "morgan stanley": "MS", "capital one": "COF", "servicenow": "NOW", "thermo fisher": "TMO", "eli lilly": "LLY" };
const COMMON = new Set(["home", "general", "american", "bank", "capital", "union", "southern", "united", "texas", "advanced", "applied", "morgan", "wells", "philip", "charles", "international", "johnson", "booking", "target", "service", "data", "first", "next", "walt", "lam", "intuitive", "eli", "thermo", "goldman", "procter", "palo", "duke", "coca-cola", "berkshire", "linde", "boeing"]);
const STOPNAMES =new Set(["the", "inc", "inc.", "company", "corporation", "co.", "&", "plc", "group", "class", "(class", "a)", "b)", "c)"]);

export function companiesIn(q) {
  const s = " " + q.toLowerCase() + " ", out = [];
  for (const [k, t] of Object.entries(ALIAS)) if (s.includes(k)) out.push(t);
  for (const [t, name] of UNIVERSE) {
    const full = name.toLowerCase().replace(/\((the|class [abc])\)|,? inc\.?|\bcorporation\b|\bcompany\b|\bplc\b|\bco\.$/g, "").replace(/\s+/g, " ").trim();
    if (full.length > 3 && s.includes(" " + full)) { out.push(t); continue; }
    const first = name.toLowerCase().split(/\s+/).filter(w => !STOPNAMES.has(w))[0]?.replace(/[,.]$/, "");
    if (first && first.length > 2 && !COMMON.has(first) && new RegExp(`[^a-z]${first.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^a-z]|'s)`).test(s)) out.push(t);
    if (t.length >= 3 && new RegExp(`(^|[^A-Za-z])${t.replace(".", "\\.")}([^A-Za-z]|$)`).test(q)) out.push(t);   // ticker in capitals
  }
  return [...new Set(out)];
}

export function datesIn(q, C) {
  const s = q.toLowerCase(), all = C.dates.filter(d => d <= C.day), out = [];
  for (const m of s.matchAll(/\b(20\d\d-\d\d-\d\d)\b/g)) out.push(m[1]);
  const year = C.day.slice(0, 4);
  for (const m of s.matchAll(/\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:de\s+)?([a-zç]{3,10})\b/g)) { const mo = MONTHS[m[2]] || MONTHS[m[2].slice(0, 3)]; if (mo && +m[1] <= 31) out.push(`${year}-${String(mo).padStart(2, "0")}-${m[1].padStart(2, "0")}`); }
  for (const m of s.matchAll(/\b([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b/g)) { const mo = MONTHS[m[1]] || MONTHS[m[1].slice(0, 3)]; if (mo && m[1].length >= 3 && +m[2] <= 31 && !/^(day|top|the|and|for|last|first|was|who|has)$/.test(m[1])) out.push(`${year}-${String(mo).padStart(2, "0")}-${m[2].padStart(2, "0")}`); }
  let range = null;
  if (/\b(yesterday|last night|ontem|ayer|today|hoje|hoy|latest|this morning)\b/.test(s)) out.push(all[all.length - 1]);
  if (/\b(this week|esta semana|the week|since monday|past few days|recently|lately)\b/.test(s)) {
    const last = new Date(all[all.length - 1] + "T12:00:00Z"), mon = new Date(last); mon.setUTCDate(last.getUTCDate() - ((last.getUTCDay() + 6) % 7));
    range = all.filter(d => d >= mon.toISOString().slice(0, 10));
  }
  if (/\b(since the start|since the beginning|so far|from the start|desde o início|desde el inicio)\b/.test(s)) range = all.slice(1);
  if (/\b(first (trading )?day|day zero|primeiro dia)\b/.test(s)) out.push(/trading/.test(s) ? all[1] : all[0]);
  return { dates: [...new Set(out)].filter(Boolean), range };
}

export function understand(q, C, history = [], screen = {}) {
  const s = q.toLowerCase();
  const names = [...C.P].sort((a, b) => b.name.length - a.name.length);
  let agents = [];
  for (const p of names) { const re = new RegExp(`\\b${p.name.toLowerCase().replace(/[^a-z0-9]+/g, "[ -]?")}\\b`); if (re.test(s)) agents.push(p.id); }
  const ghost = [...q.matchAll(/\b([A-Z][a-z]+)[ -]?(\d{1,2})\b/g)].map(m => `${m[1]}-${m[2].padStart(2, "0")}`).filter(n => !C.P.some(p => p.name.toLowerCase() === n.toLowerCase()) && !/^(Nov|Dec|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Day|Top)-/i.test(n));
  if (/\b(leader|leading|winning|first place|number one|best agent|ganhar|lidera|ganando)\b/.test(s) && !agents.length && /\b(it|its|why|what|own|hold|buy|bought)\b/.test(s) && /\bthe (leader|winner)\b/.test(s)) agents.push(C.ranked[0]?.id);
  const species = Object.keys(C.A.species).filter(sp => new RegExp(`\\b${sp}s?\\b(?![ -]?\\d)`).test(s));
  let companies = companiesIn(q);
  const { dates, range } = datesIn(q, C);
  const last = history[history.length - 1] || {};
  const pronoun = /\b(it|its|it's|they|them|their|this one|that one|that agent|this agent|the same|ele|ela|dele|dela|eles|esse|essa|este|esta|lo|la|él|ella)\b/.test(s);
  const focusUsed = {};
  if (!agents.length && !companies.length && pronoun) {
    if (last.focus?.agent && C.byId[last.focus.agent]) { agents = [last.focus.agent]; focusUsed.agent = true; }
    else if (last.focus?.company) { companies = [last.focus.company]; focusUsed.company = true; }
    else if (screen.agent && C.byId[screen.agent]) { agents = [screen.agent]; focusUsed.agent = true; }
  }
  if (agents.length === 1 && /\b(them|both|compare|versus|vs\.?|against)\b/.test(s) && last.focus?.agent && last.focus.agent !== agents[0] && /\b(compare|vs|versus|against)\b/.test(s)) agents.push(last.focus.agent);
  const advice = /\b(should i|shall i|would you|do you recommend|recommend|worth buying|good investment|good buy|buy for real|for real|my own money|my money|my savings|invest in|which stock|what stock|what share|stock to buy|tell me what to buy|devo|deveria|investir|em que ação|que ações|qual ação|debo|debería|invertir|qué acción)\b/.test(s)
    && !/\bwhy did\b/.test(s);
  const command = /^\s*(show( me)?|open|take me|go to|display|zoom|jump|mostra|abre|leva-me|muestra|abre|ve a)\b/.test(s);
  const views = { journal: /\b(journal|newspaper|jornal)\b/, evolution: /\b(evolution|family tree|tree)\b/, world: /\b(world|globe|map)\b/, network: /\b(network|graph)\b/, people: /\b(people|insiders?|politicians?)\b/, lab: /\b(lab|evidence)\b/, race: /\b(race|ranking|podium)\b/, detail: /\b(holdings|portfolio|owns?|positions)\b/ };
  const view = Object.entries(views).find(([, re]) => re.test(s))?.[0];
  const isWh = /\b(who|what|why|how|which|when|where|is|are|does|did|do|can|quem|o que|porque|porquê|como|qual|quando|quién|qué|por qué|cómo|cuál)\b/.test(s);
  const vague = q.trim().split(/\s+/).length <= 6 && !agents.length && !companies.length && !species.length && !dates.length && !range && (pronoun || /^\s*(compare( them| these| those)?|and\??|how about|what about)\s*[.?!]*\s*$/.test(s))
    && !/\b(market|agents|monkeys|index|s&p|everyone|anyone|all)\b/.test(s);

  // plan: which tools to call before asking the model
  const plan = [];
  const add = (tool, args = {}) => { if (!plan.some(x => x.tool === tool && JSON.stringify(x.args) === JSON.stringify(args))) plan.push({ tool, args }); };
  const T = (re) => re.test(s);
  if (ghost.length && !agents.length) { /* unknown agent: no tool; the model says so */ }
  if (agents.length >= 2) add("compare_agents", { agents });
  for (const a of agents.slice(0, 2)) {
    if (agents.length === 1 || !T(/\bcompare|vs|versus\b/)) add("get_agent", { agent: a });
    if (companies.length) companies.slice(0, 2).forEach(c => add("explain_decision", { agent: a, company: c }));
    else if (T(/\b(why|porque|porquê|por qué|reason|explain)\b/) && T(/\b(buy|bought|sell|sold|selling|buying|trade|traded|trading|decision|purchase|order|comprou|vendeu|compró|vendió)\b/) && !T(/\bwhy (is|are) .* (winning|ahead|leading|losing|last|behind|doing)\b/)) add("explain_decision", { agent: a, date: dates[0] });
    if (T(/\b(luck|monkey|percentile|significan|skill|real|trust|sorte|suerte)\b/)) add("luck_test", { agent: a });
  }
  for (const c of companies.slice(0, 2)) if (!agents.length) add("company_story", { company: c });
  if ((species.length || /\b(group|species|kind of agents|famil(y|ies)|grupo|espécie|especie)\b/.test(s)) && !agents.length) add("species");
  if (T(/\b(win|winning|winner|lead|leader|leading|ahead|first|last|losing|loser|worst|best|rank|ranking|podium|beat|beats|beating|making money|made money|top|bottom|ganhar|perder|ganando|perdiendo|lidera|melhor|pior|mejor|peor|anyone|everyone|nobody)\b/) && !companies.length) add("ranking");
  if (T(/\b(group|species|kind of agents|family|families|type of agents|grupo|espécie|especie)\b/)) add("species");
  if (T(/\b(market|markets|s&p|index|sector|sectors|dollar|euro|fell|fall|rose|rise|crash|happened|yesterday|today|week|day|mercado|bolsa|ontem|ayer|semana)\b/) && !agents.length || dates.length && !agents.length && !companies.length) add("market_summary", { dates: range || (dates.length ? dates : null) });
  if (T(/\b(luck|monkey|monkeys|random|chance|sorte|macaco|suerte|mono)\b/) && !agents.length) add("luck_test", {});
  if (T(/\b(brake|stop loss|stop-loss|travão)\b/)) add("pending_orders");
  if (T(/\b(tomorrow|next open|pending|will .* trade|going to (buy|sell)|orders?|selling|amanhã|mañana)\b/)) add("pending_orders");
  if (T(/\b(most agents|most popular|most owned|most held|held by the most|fees|paid in fees|total fees|commissions)\b/)) add("holdings_overview");
  if (T(/\b(evolution|eliminat|die|dies|death|graveyard|born|birth|children|child|generation|selection|weakest|survive|elimina|morre)\b/)) add("evolution");
  if (T(/\b(signal|signals|lab|tested|testing|shadow|admitted|use news|uses news)\b/)) add("lab");
  if (T(/\b(insider|insiders|politician|politicians|congress|senator|disclos)\b/)) add("people", { company: companies[0] });
  if (T(/\b(news|headline|brief|world|war|iran|conflict|notícias|noticias)\b/) || (T(/\bwhy\b/) && plan.some(x => x.tool === "market_summary"))) add("find_news", { words: q.split(/\W+/).filter(w => w.length > 4).slice(0, 4), date: dates[0] || null });
  if (T(/\b(what is|what's|what are|what does|mean|means|meaning|explain|how does|how do|rule|rules|cost|costs|fee|fees|real money|dna|brake|stop loss|review|o que é|qué es|significa)\b/) || advice) add("rules", { topic: q });
  if (!plan.length && !vague) { add("ranking"); add("rules", { topic: q }); }

  const go = command ? {
    ...(agents[0] ? { agent: agents[0] } : {}), ...(companies[0] && !agents[0] ? { company: companies[0] } : {}),
    ...(dates[0] ? { date: dates[0] } : {}), ...(view ? { view: view === "detail" && !agents[0] ? undefined : view } : agents[0] ? { view: "story" } : {}),
  } : null;
  if (go) Object.keys(go).forEach(k => go[k] === undefined && delete go[k]);

  return { agents, companies, species, dates, range, ghost, advice, command, go: go && Object.keys(go).length ? go : null, vague: vague && !command, isWh, focusUsed, plan: plan.slice(0, 5) };
}
