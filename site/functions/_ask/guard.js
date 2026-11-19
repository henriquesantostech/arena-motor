// Ask v2 guards: nothing reaches the reader with raw ids, advice, or numbers we do not have.
export const RAW_ID = [/\s*\[[^\]]{0,80}\]/g, /\b(m|p|day|world|people|species):[a-z0-9][a-z0-9:._-]*/gi, /\bwce:[0-9a-f]+/gi, /\b[a-z_]+_rss:[0-9a-f]+/gi];
export const ADVICE = [
  /\byou (should|ought to|could|might want to|may want to|need to) (buy|sell|invest in|hold|short|get into|consider buying|consider selling)\b/i,
  /\b(i|we) (recommend|suggest|advise) (buying|selling|that you buy|that you sell|you buy|you sell|investing)\b/i,
  /\b(strong buy|good buy|good time to buy|worth buying|a great investment|a good investment for you)\b/i,
  /\b(deve|deves|devia|devias|recomendo|aconselho) (comprar|vender|investir)\b/i,
  /\b(deber[ií]a|deber[ií]as|recomiendo|aconsejo) (comprar|vender|invertir)\b/i,
];
export const normalise = s => String(s || "").replace(/[‐‑]/g, "-").replace(/[‒–−](?=\s?\d)/g, "-").replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/[    ]/g, " ");
export const clean = s => RAW_ID.reduce((t, re) => t.replace(re, ""), normalise(s)).replace(/\s+([.,;:!?])/g, "$1").replace(/\s{2,}/g, " ").trim();
export const hasAdvice = s => ADVICE.some(re => re.test(s));

// Numbers: every number the model writes must be in the facts it was given (rounding allowed).
const NUM = /(?<![\w.])-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:[.,]\d+)?\s*(?:k\b|%)?/gi;
function parse(tok) {
  let t = tok.trim().toLowerCase(), k = 1;
  if (t.endsWith("k")) { k = 1000; t = t.slice(0, -1).trim(); }
  t = t.replace("%", "").trim();
  const out = [];
  if (/^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(t)) out.push(parseFloat(t.replace(/,/g, "")));
  else if (/^-?\d+,\d{1,2}$/.test(t)) out.push(parseFloat(t.replace(",", ".")));   // 1,5 (pt/es decimals)
  else out.push(parseFloat(t.replace(/,/g, "")));
  return out.filter(Number.isFinite).map(x => Math.abs(x * k));
}
export function numbersIn(text) { return [...String(text).matchAll(NUM)].flatMap(m => parse(m[0])); }
export function groundSet(texts) {
  const S = new Set();
  const add = x => { for (const d of [0, 1, 2]) S.add((Math.round(x * 10 ** d) / 10 ** d).toFixed(d)); };
  for (const t of texts) for (const n of numbersIn(t)) { add(n); if (n >= 1000) { add(n / 1000); add(Math.round(n / 100) * 100); } }
  return S;
}
export function ungrounded(text, S) {
  const bad = [];
  for (const n of numbersIn(text)) {
    if (n <= 31 && Number.isInteger(n)) continue;            // counts, days of the month
    if (n >= 2020 && n <= 2030 && Number.isInteger(n)) continue;   // years
    const d = String(n).includes(".") ? Math.min(2, String(n).split(".")[1].length) : 0;
    if (!S.has(n.toFixed(d))) bad.push(n);
  }
  return bad;
}
