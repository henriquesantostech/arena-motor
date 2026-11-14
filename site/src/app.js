// Arena of Agents: one-look page. Reads window.ARENA (data.js), draws the HUD at once,
// then loads the 3D scene (arena3d.js). Falls back to the 2D view without WebGL.
/* global ARENA_3D_URL */
(function () {
  "use strict";
  performance.mark("arena:app");
  const A = window.ARENA || { meta: { dates: [] }, species: {}, p: [], band: [], day: null };
  const $ = s => document.querySelector(s);
  const css = getComputedStyle(document.documentElement);
  const COLORS = {};
  ["trend", "contrarian", "value", "news", "balanced", "monkey", "equal", "index"].forEach(k => COLORS[k] = css.getPropertyValue("--" + k).trim());
  const SPECIES = Object.keys(A.species);
  const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } } };

  // ---------- formatting ----------
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const nf = (x, d = 0) => x == null ? "—" : x.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
  const eur = (x, d = 0) => x == null ? "—" : (x < 0 ? "−€" : "€") + nf(Math.abs(x), d);
  const pct = (x, d = 1, sign = true) => x == null ? "—" : (sign && x > 0 ? "+" : x < 0 ? "−" : "") + nf(Math.abs(x * 100), d) + "%";
  const ud = x => x == null || Math.abs(x) < 5e-5 ? "" : x > 0 ? "up" : "down";
  const day = d => d ? new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }) : "—";
  const dayY = d => d ? new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "—";
  const colorOf = p => p.type === "agent" ? COLORS[p.sp] : COLORS[p.type];
  const label = p => p.type === "index" ? "S&P 500" : p.type === "equal" ? "Equal weight" : p.type === "monkey" ? "Monkey " + (p.name.match(/\d+/) || [""])[0] : p.name;
  const shape = p => p.type === "agent" ? `<span class="gem" style="background:${colorOf(p)}"></span>` : `<span class="dot" style="background:${colorOf(p)}"></span>`;

  // ---------- model ----------
  const P = A.p, byId = Object.fromEntries(P.map(p => [p.id, p]));
  const agents = P.filter(p => p.type === "agent"), monkeys = P.filter(p => p.type === "monkey");
  const idx = P.find(p => p.type === "index"), eqw = P.find(p => p.type === "equal");
  const scored = agents.length && agents.every(p => p.score != null);
  const ranked = agents.slice().sort((a, b) => scored ? b.score - a.score : (b.vsIdx ?? b.ret ?? 0) - (a.vsIdx ?? a.ret ?? 0) || a.name.localeCompare(b.name));
  ranked.forEach((p, i) => p.rank = i + 1);
  const moved = agents.some(p => Math.abs(p.ret || 0) > 1e-6);
  const order = [...ranked, ...(idx ? [idx] : []), ...(eqw ? [eqw] : []), ...monkeys.slice().sort((a, b) => (b.ret || 0) - (a.ret || 0))];
  const gap = p => p.type === "index" ? 0 : p.vsIdx;
  const model = {
    capital: A.meta.capital || 100000, speciesOrder: SPECIES, monkeys: monkeys.length,
    speciesLabel: Object.fromEntries(SPECIES.map(s => [s, A.species[s].label])),
    perSpecies: {}, items: [],
  };
  agents.forEach(p => { p.slot = model.perSpecies[p.sp] = (model.perSpecies[p.sp] ?? -1) + 1; });
  Object.keys(model.perSpecies).forEach(k => model.perSpecies[k]++);
  monkeys.forEach((p, i) => p.slot = i);
  const lastDay = A.meta.updated;
  P.forEach(p => p.active = p.type !== "index" && p.type !== "equal" && p.log.some(l => l.d === lastDay && (l.k === "buy" || l.k === "sell")));
  const mg = monkeys.map(p => p.vsIdx).filter(v => v != null);
  model.luck = mg.length && moved ? [Math.min(...mg), Math.max(...mg)] : null;
  P.forEach(p => model.items.push({ id: p.id, type: p.type, sp: p.sp, slot: p.slot, value: p.value, gap: gap(p), active: p.active, rank: p.type === "agent" && moved ? p.rank : 0 }));

  // ---------- HUD ----------
  const nDay = Math.max(0, (A.meta.dates || []).length - 1);
  $("#status").textContent = A.meta.updated
    ? `${A.meta.mode === "trial" ? "Trial" : "Live"} · Day ${nDay} · Close ${dayY(A.meta.updated)}`
    : "Opens after the first night";

  function kpis() {
    const above = agents.filter(p => (p.vsIdx || 0) > 0).length;
    const mAbove = monkeys.filter(p => (p.vsIdx || 0) > 0).length;
    const best = ranked[0];
    const d = A.day;
    $("#kpis").innerHTML = [
      idx && `<div class="kpi glass click" data-id="${idx.id}" title="The benchmark: S&P 500 with dividends, in euros. It is the water line."><div class="l"><span class="wave"></span>S&P 500</div><div class="v ${ud(idx.ret)}">${pct(idx.ret)}<small>since ${day(idx.from)}</small></div></div>`,
      `<div class="kpi glass" title="Agents beating the S&P 500 since day zero."><div class="l">Agents above water</div><div class="v">${above}<small>/ ${agents.length}</small></div></div>`,
      `<div class="kpi glass" title="Monkeys pick at random. If they beat the index too, beating it proves little."><div class="l">Monkeys above water</div><div class="v">${mAbove}<small>/ ${monkeys.length}</small></div></div>`,
      best && moved ? `<div class="kpi glass click" data-id="${best.id}"><div class="l">${shape(best)}Leader</div><div class="v">${esc(best.name)}<small class="${ud(best.vsIdx)}">${pct(best.vsIdx)}</small></div></div>`
        : `<div class="kpi glass"><div class="l">Last night</div><div class="v">${d ? d.buys + d.sells : 0}<small>trades</small></div></div>`,
    ].filter(Boolean).join("");
  }

  function board() {
    const max = Math.max(0.0001, ...order.map(p => Math.abs(gap(p) || 0)));
    const row = (p, extra = "", name = label(p)) => {
      const g = gap(p), w = Math.abs(g || 0) / max * 20;
      const bar = p.type === "index" ? `<span class="trk"></span><span class="pc mute">water</span>` :
        `<span class="trk"><i style="${g >= 0 ? "left:50%" : "right:50%"};width:${w}px;background:${g >= 0 ? "var(--up)" : "var(--down)"}"></i></span><span class="pc ${ud(g)}">${pct(g)}</span>`;
      return `<button class="row ${extra}" data-id="${p.id}"><span class="n">${p.type === "agent" ? p.rank : ""}</span>${shape(p)}<span class="nm">${esc(name)}</span>${bar}</button>`;
    };
    const mk = monkeys.slice().sort((a, b) => (b.vsIdx || 0) - (a.vsIdx || 0));
    const mid = mk.length ? mk[Math.floor((mk.length - 1) / 2)] : null;
    $("#board").innerHTML = `<h2><span>${scored ? "Ranking · score" : "Ranking"}</span><span>vs S&P 500</span></h2><div class="rows">` +
      ranked.map(p => row(p)).join("") +
      (idx ? row(idx, "sep ref") : "") + (eqw ? row(eqw, "ref") : "") +
      (mid ? row(mid, "ref", "Monkeys · median") : "") +
      `</div>`;
  }

  function podium() {
    if (!ranked.length) { $("#podium").innerHTML = ""; return; }
    const top = [ranked[1], ranked[0], ranked[2]].filter(Boolean);
    const anyMerit = ranked.slice(0, 3).some(p => p.merit);
    $("#podium").innerHTML = `<div class="pod-wrap"><div class="pod-cap">${anyMerit ? "Podium" : "Podium · provisional"}</div><div style="display:flex;align-items:flex-end;gap:10px">` +
      top.map(p => `<button class="step glass p${p.rank}" data-id="${p.id}"><div class="who">${shape(p)}${esc(p.name)}</div><div class="pct ${ud(p.vsIdx)}">${moved ? pct(p.vsIdx) : "±0%"}</div><div class="base">${p.rank}</div></button>`).join("") +
      `</div></div>`;
  }

  function legend() {
    $("#legend").className = "legend glass";
    $("#legend").innerHTML = SPECIES.map(s => `<span><span class="gem" style="background:${COLORS[s]}"></span>${esc(A.species[s].label)}</span>`).join("") +
      `<span><span class="dot" style="background:${COLORS.monkey}"></span>Monkeys</span><span><span class="dot" style="border:2px solid #fff;background:none"></span>Equal weight</span><span><span class="wave"></span>S&P 500</span>`;
  }

  kpis(); board(); podium(); legend();
  performance.mark("arena:ui");

  // ---------- tooltip + highlight ----------
  const tip = $("#tip");
  let view = null;
  function showTip(id, ev) {
    const p = byId[id];
    if (!p || !ev) { tip.hidden = true; return; }
    tip.innerHTML = `<b>${esc(label(p))}</b>${p.type === "agent" ? ` <span class="mute">· ${esc(A.species[p.sp].label)}</span>` : ""}<br>${eur(p.value)} · <span class="${ud(p.ret)}">${pct(p.ret)}</span>` +
      (p.type !== "index" ? ` · vs index <span class="${ud(p.vsIdx)}">${pct(p.vsIdx)}</span>` : "");
    tip.hidden = false;
    const x = Math.min(ev.clientX, innerWidth - tip.offsetWidth - 24), y = Math.min(ev.clientY, innerHeight - tip.offsetHeight - 24);
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  function hover(id, ev) {
    showTip(id, ev);
    document.querySelectorAll(".row.hl").forEach(r => r.classList.remove("hl"));
    if (id) document.querySelectorAll(`.row[data-id="${id}"]`).forEach(r => r.classList.add("hl"));
  }
  document.addEventListener("click", ev => {
    const t = ev.target.closest("[data-id]");
    if (t && !ev.target.closest(".veil")) { open(t.dataset.id); }
  });
  $("#board").addEventListener("pointerover", ev => { const r = ev.target.closest(".row"); if (r && view && view.highlight) view.highlight(r.dataset.id); });
  $("#board").addEventListener("pointerleave", () => view && view.highlight && view.highlight(null));
  $("#rankbtn").addEventListener("click", () => $("#board").classList.toggle("open"));

  // ---------- views ----------
  const stage = $("#stage");
  const hasGL = (() => { try { const c = document.createElement("canvas"); return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl"))); } catch (e) { return false; } })();
  let mode = store.get("arena.view") || (hasGL ? "3d" : "2d");
  if (!hasGL) { mode = "2d"; $("#v3d").disabled = true; $("#v3d").title = "3D is not available on this device"; }

  function load3d() {
    return new Promise((ok, fail) => {
      if (window.Arena3D) return ok(window.Arena3D);
      const s = document.createElement("script");
      s.src = typeof ARENA_3D_URL === "string" ? ARENA_3D_URL : "arena3d.js";
      s.onload = () => window.Arena3D ? ok(window.Arena3D) : fail(new Error("3D did not start"));
      s.onerror = fail; document.head.appendChild(s);
    });
  }
  function setMode(m) {
    mode = m; store.set("arena.view", m);
    $("#v3d").setAttribute("aria-pressed", m === "3d"); $("#v2d").setAttribute("aria-pressed", m === "2d");
    if (view) { view.destroy(); view = null; }
    stage.innerHTML = "";
    if (m === "3d") {
      load3d().then(lib => {
        if (mode !== "3d") return;
        view = lib.mount(stage, model, { colors: COLORS, onPick: open, onHover: hover });
        requestAnimationFrame(() => { performance.mark("arena:3d"); report(); });
      }).catch(() => setMode("2d"));
    } else { view = flat(stage); performance.mark("arena:2d"); report(); }
  }
  $("#v3d").addEventListener("click", () => mode !== "3d" && setMode("3d"));
  $("#v2d").addEventListener("click", () => mode !== "2d" && setMode("2d"));

  // 2D view: same encoding as 3D, seen from the side. Columns = species, then monkeys and equal weight.
  function flat(host) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg"); host.appendChild(svg);
    const cols = [...SPECIES, "monkey", "equal"];
    function draw() {
      const W = host.clientWidth, H = host.clientHeight, phone = W < 820;
      const m = phone ? { l: 16, r: 16, t: 150, b: 210 } : { l: 300, r: 310, t: 110, b: 240 };
      const pw = W - m.l - m.r, ph = H - m.t - m.b, y0 = m.t + ph / 2;
      const span = Math.max(0.04, ...P.map(p => Math.abs(gap(p) || 0)));
      const y = g => y0 - (Math.max(-1, Math.min(1, (g || 0) / span))) * (ph / 2 - 16);
      const cw = pw / cols.length;
      let s = `<defs><linearGradient id="wg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${COLORS.index}" stop-opacity=".22"/><stop offset="1" stop-color="${COLORS.index}" stop-opacity="0"/></linearGradient></defs>`;
      s += `<rect x="${m.l}" y="${y0}" width="${pw}" height="${ph / 2}" fill="url(#wg)"/>`;
      s += `<line x1="${m.l}" x2="${m.l + pw}" y1="${y0}" y2="${y0}" stroke="${COLORS.index}" stroke-width="2"/>`;
      s += `<text x="${m.l + 4}" y="${y0 + 16}" fill="${COLORS.index}" font-size="12" font-weight="600">S&amp;P 500 · the water</text>`;
      [1, -1].forEach(k => s += `<text x="${m.l + 4}" y="${y(k * span) + (k > 0 ? -6 : 14)}" fill="#5b6479" font-size="11">${pct(k * span, 0)}</text>`);
      cols.forEach((c, i) => {
        const cx = m.l + cw * (i + 0.5);
        const lab = c === "monkey" ? "Monkeys" : c === "equal" ? "Equal" : A.species[c].label;
        s += `<text x="${cx}" y="${m.t + ph + 22}" text-anchor="middle" fill="${COLORS[c]}" font-size="${phone ? 9.5 : 12}" font-weight="600">${esc(phone && lab.length > 7 ? lab.slice(0, 6) + "." : lab)}</text>`;
        const group = P.filter(p => c === "monkey" ? p.type === "monkey" : c === "equal" ? p.type === "equal" : p.type === "agent" && p.sp === c);
        group.forEach((p, k) => {
          const off = group.length > 1 ? (k / (group.length - 1) - 0.5) * Math.min(cw * 0.6, 14 * group.length) : 0;
          const r = p.type === "agent" ? 7 * Math.max(0.7, Math.min(1.6, Math.pow((p.value || model.capital) / model.capital, 2.2))) : 5;
          const cy = y(gap(p));
          s += `<line x1="${cx + off}" x2="${cx + off}" y1="${y0}" y2="${cy}" stroke="${COLORS[c]}" stroke-opacity=".35"/>`;
          s += p.type === "agent"
            ? `<path data-id="${p.id}" d="M${cx + off} ${cy - r * 1.4}L${cx + off + r} ${cy}L${cx + off} ${cy + r * 1.4}L${cx + off - r} ${cy}Z" fill="${COLORS[c]}" style="cursor:pointer"/>`
            : `<circle data-id="${p.id}" cx="${cx + off}" cy="${cy}" r="${r}" fill="${p.type === "equal" ? "none" : COLORS[c]}" stroke="${p.type === "equal" ? "#fff" : "none"}" stroke-width="2" style="cursor:pointer"/>`;
        });
      });
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = s;
    }
    draw();
    const ro = new ResizeObserver(draw); ro.observe(host);
    svg.addEventListener("pointermove", ev => { const t = ev.target.closest("[data-id]"); hover(t ? t.dataset.id : null, ev); });
    svg.addEventListener("pointerleave", () => hover(null));
    return { destroy() { ro.disconnect(); svg.remove(); }, highlight() {}, pause() {} };
  }

  // ---------- card ----------
  const card = $("#card");
  let current = null;
  function open(id) {
    const p = byId[id]; if (!p) return;
    current = p; tip.hidden = true; $("#board").classList.remove("open");
    if (location.hash !== "#/" + id) history.replaceState(null, "", "#/" + id);
    card.innerHTML = sheet(p); card.hidden = false;
    view && view.pause && view.pause(true);
    requestAnimationFrame(() => { drawChart(p); drawRadar(p); drawTiles(p); });
    card.querySelector(".close").focus({ preventScroll: true });
  }
  function close() {
    card.hidden = true; current = null; view && view.pause && view.pause(false);
    history.replaceState(null, "", location.pathname + location.search);
  }
  function step(k) { if (!current) return; const i = order.indexOf(current); open(order[(i + k + order.length) % order.length].id); }
  card.addEventListener("click", ev => {
    if (ev.target === card || ev.target.closest(".close")) close();
    else if (ev.target.closest(".prev")) step(-1); else if (ev.target.closest(".next")) step(1);
  });
  document.addEventListener("keydown", ev => {
    if (ev.key === "Escape") { if (!card.hidden) close(); else if (!$("#howto").hidden) $("#howto").hidden = true; }
    if (!card.hidden && ev.key === "ArrowRight") step(1);
    if (!card.hidden && ev.key === "ArrowLeft") step(-1);
  });

  function sheet(p) {
    const isAgent = p.type === "agent";
    const sub = isAgent ? `${A.species[p.sp].label} · ${A.species[p.sp].about}` :
      p.type === "monkey" ? "Control: picks at random" : p.type === "index" ? "Benchmark: the water line" : "Benchmark: all companies, equal parts";
    const badge = isAgent ? (p.merit ? `<span class="badge merit">Merit</span>` : `<span class="badge">Provisional</span>`) : "";
    const tiles = [
      ["Value", eur(p.value), ""],
      ["Return", pct(p.ret, 2), ud(p.ret)],
      ["vs S&P 500", p.type === "index" ? "—" : pct(p.vsIdx, 2), ud(p.vsIdx)],
      [p.type === "monkey" || p.type === "index" ? "Rank" : "Beats monkeys", isAgent || p.type === "equal" ? (p.beatsMonkeys == null ? "—" : nf(p.beatsMonkeys * 100) + "%") : "—", ""],
      ["Worst drop", p.mdd ? pct(-p.mdd, 1) : "0%", p.mdd > 0.0001 ? "down" : ""],
      [isAgent ? "Rank · score" : "Days", isAgent ? `#${p.rank}${p.score != null ? ` · ${nf(p.score, 2)}` : ""}` : nf(p.days), ""],
    ];
    const hold = p.hold.length ? `<div class="tiles" id="tiles"></div>` : `<div class="empty">All in cash</div>`;
    const moves = [
      ...p.next.map(o => ({ d: "next", k: "next", side: o.k, t: o.t, eur: o.eur, why: o.why })),
      ...p.log,
    ].slice(0, 14).map(l => `<div class="lrow"><span class="mute">${l.d === "next" ? "Next open" : day(l.d)}</span><span class="k-${l.k}">${l.k === "next" ? l.side : l.k}</span><b>${esc(l.t.replace("^SP500TR", "S&P TR"))}</b><span>${l.eur != null ? eur(l.eur) : l.ratio ? "×" + l.ratio : ""}</span><span class="why" title="${esc(l.why || "")}">${esc(l.why || "")}</span></div>`).join("")
      || `<div class="empty">No moves yet. Orders are placed at night and filled at the next open.</div>`;
    const dnaPane = isAgent ? `<h3><span>DNA · what it values</span><span class="k">${p.dna.picks} stocks · review ${p.dna.review}d · ${p.dna.stop ? "stop " + pct(-p.dna.stop, 0) : "no stop-loss"}</span></h3><div class="fill" id="radar"></div>` :
      `<h3><span>How it works</span></h3><div class="empty" style="font-size:13.5px;line-height:1.55;color:var(--mute)">${p.type === "monkey"
        ? `Same rules as <b style="color:var(--text)">${esc(p.copies || "an agent")}</b> (how many stocks, when to review, when to cut), but every pick is random. If an agent cannot beat its monkey, its skill is luck.`
        : p.type === "index" ? "The S&P 500 with dividends, in euros, bought on day zero with the same costs. Agents above the water are beating it."
          : "Equal parts in every company of the universe, never touched. Shows whether picking companies adds anything."}</div>`;
    const extra = [`Volatility ${pct(p.vol, 1, false)}`, `Fees ${eur(p.fees, 2)}`, `Dividends ${eur(p.divs, 2)}`,
      `Turnover ${p.turnover != null ? nf(p.turnover, 1) + "×/yr" : "—"}`, `Win rate ${p.hit == null ? "—" : pct(p.hit, 0, false)}`, `Est. tax ${eur(p.tax, 0)}`, `Born ${dayY(p.born)}`].join(" · ");
    return `<article class="sheet" role="dialog" aria-modal="true" aria-label="${esc(label(p))}">
      <div class="hd">${isAgent ? `<span class="gem" style="background:${colorOf(p)}"></span>` : shape(p)}<div><h1>${esc(label(p))}</h1><div class="about">${esc(sub)}</div></div>${badge}</div>
      <div class="nav"><button class="prev" aria-label="Previous">‹</button><button class="next" aria-label="Next">›</button><button class="close" aria-label="Close">✕</button></div>
      <div class="big">${tiles.map(t => `<div><div class="l">${t[0]}</div><div class="v ${t[2]}">${t[1]}</div></div>`).join("")}</div>
      <section class="pane chart"><h3><span>Since day zero</span><span class="k"><span><span class="dot" style="background:${colorOf(p)}"></span>${esc(label(p))}</span>${p.type !== "index" ? `<span><span class="dot" style="background:${COLORS.index}"></span>S&P 500</span>` : ""}<span><span class="dot" style="background:${COLORS.monkey};opacity:.6"></span>Monkeys</span></span></h3><div class="fill" id="chart"></div></section>
      <section class="pane dna">${dnaPane}</section>
      <section class="pane hold"><h3><span>Holdings · ${p.hold.length}</span><span class="k" title="Tile size = share of the portfolio; colour = gain since bought">size = weight · colour = gain</span></h3><div class="fill" style="overflow:hidden">${hold}</div></section>
      <section class="pane log"><h3><span>Latest moves</span><span class="k">filled at the open, after the night's decision</span></h3><div class="fill" style="overflow:hidden">${moves}</div></section>
      <div class="foot">${extra}</div>
    </article>`;
  }

  function box(el) { const r = el.getBoundingClientRect(); return [Math.max(160, r.width), Math.max(120, r.height)]; }

  function drawChart(p) {
    const el = card.querySelector("#chart"); if (!el) return;
    const [W, H] = box(el), m = { l: 44, r: 8, t: 8, b: 20 };
    const dates = A.meta.dates, o = Math.max(0, dates.indexOf(p.from));
    const base = p.s[0] || 1, mine = p.s.map(v => v / base - 1);
    const ix = idx && p.type !== "index" ? idx.s.slice(o).map((v, i, a) => v / a[0] - 1) : [];
    const band = (A.band || []).slice(o).map(b => b && [b[0] / model.capital - 1, b[1] / model.capital - 1]);
    const all = [0, ...mine, ...ix, ...band.flat().filter(v => v != null)];
    let lo = Math.min(...all), hi = Math.max(...all); if (hi - lo < 0.01) { hi += 0.005; lo -= 0.005; }
    const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
    const n = Math.max(mine.length, 2);
    const X = i => m.l + (W - m.l - m.r) * (i / (n - 1)), Y = v => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
    const line = (a, c, w, extra = "") => `<polyline points="${a.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ")}" fill="none" stroke="${c}" stroke-width="${w}" stroke-linejoin="round" ${extra}/>`;
    let s = "";
    [lo + pad, 0, hi - pad].forEach(v => { s += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="rgba(140,160,210,${v === 0 ? .3 : .1})"/><text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end" fill="#5b6479" font-size="10.5">${pct(v, 1)}</text>`; });
    const bf = band.map((b, i) => b && [i, b]).filter(Boolean);
    if (bf.length > 1) s += `<polygon points="${bf.map(([i, b]) => `${X(i)},${Y(b[1])}`).join(" ")} ${bf.slice().reverse().map(([i, b]) => `${X(i)},${Y(b[0])}`).join(" ")}" fill="${COLORS.monkey}" opacity=".18"/>`;
    if (ix.length > 1) s += line(ix, COLORS.index, 1.6, `stroke-dasharray="4 3"`);
    if (mine.length > 1) s += line(mine, colorOf(p) || "#fff", 2.4);
    else s += `<text x="${(W + m.l) / 2}" y="${H / 2}" text-anchor="middle" fill="#5b6479" font-size="12">The line starts after the first trading day</text>`;
    [0, n - 1].forEach(i => dates[o + i] && (s += `<text x="${X(i)}" y="${H - 4}" text-anchor="${i ? "end" : "start"}" fill="#5b6479" font-size="10.5">${day(dates[o + i])}</text>`));
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}">${s}</svg>`;
  }

  // Holdings as tiles: area = weight, colour = gain since bought (green up, red down).
  function drawTiles(p) {
    const el = card.querySelector("#tiles"); if (!el) return;
    const W = el.clientWidth, H = el.clientHeight;
    const items = p.hold.filter(h => h.w > 0).map(h => ({ h, a: h.w }));
    const cash = p.cash / (p.value || 1);
    if (cash > 0.005) items.push({ h: { t: "Cash", name: "Uninvested cash", w: cash, gain: null }, a: cash });
    const tot = items.reduce((s, i) => s + i.a, 0) || 1;
    items.forEach(i => i.a = i.a / tot * W * H);
    const out = [];
    (function lay(list, x, y, w, h) {
      if (!list.length) return;
      if (list.length === 1) { out.push([list[0], x, y, w, h]); return; }
      const sum = list.reduce((s, i) => s + i.a, 0);
      let acc = list[0].a, k = 1;
      while (k < list.length - 1 && acc + list[k].a <= sum / 2) acc += list[k++].a;
      const f = acc / sum;
      if (w >= h) { lay(list.slice(0, k), x, y, w * f, h); lay(list.slice(k), x + w * f, y, w * (1 - f), h); }
      else { lay(list.slice(0, k), x, y, w, h * f); lay(list.slice(k), x, y + h * f, w, h * (1 - f)); }
    })(items, 0, 0, W, H);
    const tone = g => g == null ? "rgba(255,255,255,.06)" : g >= 0 ? `rgba(62,224,143,${0.14 + Math.min(g / 0.15, 1) * 0.5})` : `rgba(255,107,107,${0.14 + Math.min(-g / 0.15, 1) * 0.5})`;
    el.innerHTML = out.map(([i, x, y, w, h]) => {
      const big = w > 54 && h > 34, tk = esc(i.h.t.replace("^SP500TR", "S&P TR"));
      return `<div class="tile" title="${esc(i.h.name)} · ${pct(i.h.w, 1, false)}${i.h.gain != null ? " · " + pct(i.h.gain, 1) + " since bought" : ""}" style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;background:${tone(i.h.gain)}">${w > 30 && h > 16 ? `<b>${tk}</b>` : ""}${big ? `<span>${pct(i.h.w, 0, false)}${i.h.gain != null ? ` · <i class="${ud(i.h.gain)}">${pct(i.h.gain, 1)}</i>` : ""}</span>` : ""}</div>`;
    }).join("");
  }

  function drawRadar(p) {
    const el = card.querySelector("#radar"); if (!el || !p.dna) return;
    const [W, H] = box(el), keys = Object.keys(p.dna.w), N = keys.length;
    const cx = W / 2, cy = H / 2 + 2, R = Math.min(W * 0.32, H / 2 - 18);
    const mx = Math.max(1, ...keys.map(k => p.dna.w[k]));
    const pt = (i, r) => [cx + Math.sin(i / N * Math.PI * 2) * r, cy - Math.cos(i / N * Math.PI * 2) * r];
    let s = "";
    [0.33, 0.66, 1].forEach(f => s += `<polygon points="${keys.map((_, i) => pt(i, R * f).join(",")).join(" ")}" fill="none" stroke="rgba(140,160,210,.14)"/>`);
    keys.forEach((k, i) => {
      const [x, y] = pt(i, R), [lx, ly] = pt(i, R + 12), on = p.dna.w[k] > 0;
      s += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="rgba(140,160,210,.1)"/>`;
      s += `<text x="${lx}" y="${ly + 3}" font-size="10" fill="${on ? "#c9d2e6" : "#4b5367"}" text-anchor="${Math.abs(lx - cx) < 6 ? "middle" : lx > cx ? "start" : "end"}">${esc(k)}</text>`;
    });
    const c = colorOf(p);
    s += `<polygon points="${keys.map((k, i) => pt(i, R * p.dna.w[k] / mx).join(",")).join(" ")}" fill="${c}" fill-opacity=".25" stroke="${c}" stroke-width="2" stroke-linejoin="round"/>`;
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}">${s}</svg>`;
  }

  // ---------- help ----------
  const howto = $("#howto");
  $("#help").addEventListener("click", () => {
    howto.innerHTML = `<div class="help" role="dialog" aria-modal="true" aria-label="How to read">
      <h2>How to read the arena</h2>
      <div><span class="ic"><span class="gem" style="background:${COLORS.trend}"></span></span><span><b>Each crystal is an agent</b>Colour = strategy. Bigger = more money.</span></div>
      <div><span class="ic"><span class="wave"></span></span><span><b>The water is the S&P 500</b>Above the water = beating the index. Below = losing to it.</span></div>
      <div><span class="ic"><span class="dot" style="background:${COLORS.monkey}"></span></span><span><b>Grey stones are monkeys</b>Same rules, random picks. Skill means beating them.</span></div>
      <div><span class="ic"><span class="dot" style="border:2px solid #fff"></span></span><span><b>White ring: equal weight</b>Every company in equal parts, never touched.</span></div>
      <div><span class="ic">🏆</span><span><b>Podium</b>Ranked by return over the index per unit of extra risk. "Merit" only after 6 months and beating 95% of monkeys.</span></div>
      <div><span class="ic">👆</span><span><b>Click anything</b>Opens its card: value, DNA, holdings and every move with its reason.</span></div>
      <p>Each agent starts with €100,000 of simulated money on the S&P 100. Decisions are made at night and filled at the next open, with real costs. Not investment advice.</p></div>`;
    howto.hidden = false;
  });
  howto.addEventListener("click", () => { howto.hidden = true; });

  // ---------- start ----------
  function report() {
    try {
      const nav = performance.getEntriesByType("navigation")[0];
      const m = n => (performance.getEntriesByName(n)[0] || {}).startTime;
      const r = { html: m("arena:html"), ui: m("arena:ui"), scene: m("arena:3d") || m("arena:2d"), total: nav && nav.loadEventEnd };
      window.ARENA_PERF = r;
      if (/[?&]perf\b/.test(location.search)) console.table(r);
    } catch (e) { /* ignore */ }
  }
  setMode(mode);
  function route() {
    const h = location.hash.match(/^#\/(.+)$/);
    if (h && byId[h[1]]) { if (!current || current.id !== h[1]) open(h[1]); } else if (current) close();
  }
  window.addEventListener("hashchange", route);
  route();
})();
