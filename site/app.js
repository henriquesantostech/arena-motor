// Arena de Agentes: site 2D. Lê window.ARENA (dados.js) e mostra ranking, fichas e diário.
(function () {
  "use strict";
  const A = window.ARENA || { participantes: [], datas: [], diario: [] };
  const app = document.getElementById("app");
  const P = Object.fromEntries(A.participantes.map(p => [p.nome, p]));
  const CORES = { "Tendência": "var(--e-tendencia)", "Contrária": "var(--e-contraria)", "Valor e qualidade": "var(--e-valor)",
    "Notícias": "var(--e-noticias)", "Equilibrada": "var(--e-equilibrada)", "Macaco": "var(--macaco)", "Referência": "var(--texto)" };

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const nf = (x, c = 2) => x == null ? "—" : x.toLocaleString("pt-PT", { minimumFractionDigits: c, maximumFractionDigits: c });
  const eur = x => x == null ? "—" : nf(x, 2) + " €";
  const pct = (x, c = 2, sinal = true) => x == null ? "—" : (sinal && x > 0 ? "+" : "") + nf(x * 100, c) + "%";
  const cls = x => x == null ? "" : x > 0 ? "sobe" : x < 0 ? "desce" : "";
  const dataPt = d => d ? d.split("-").reverse().join("/") : "—";
  const link = n => `#/agente/${encodeURIComponent(n)}`;
  const bola = esp => `<span class="bola" style="background:${CORES[esp] || "var(--suave)"}"></span>`;

  document.getElementById("rodape").textContent = A.atualizado ? `Atualizado com o fecho de ${dataPt(A.atualizado)}.` +
    (A.arena && A.arena.modo === "ensaio" ? " Modo ensaio." : "") : "";

  // ---------- gráfico de linhas (SVG simples) ----------
  function grafico(series, opc = {}) {
    const L = 760, H = 260, m = { e: 56, d: 10, c: 10, b: 24 };
    const datas = opc.datas || [];
    const todos = series.flatMap(s => s.valores.filter(v => v != null));
    (opc.faixa || []).forEach(f => f && todos.push(f[0], f[1]));
    if (!todos.length) return "";
    let mn = Math.min(...todos), mx = Math.max(...todos);
    if (mx === mn) { mx += 1; mn -= 1; }
    const pad = (mx - mn) * 0.06; mn -= pad; mx += pad;
    const n = Math.max(...series.map(s => s.valores.length), 2);
    const x = i => m.e + (L - m.e - m.d) * (i / (n - 1));
    const y = v => m.c + (H - m.c - m.b) * (1 - (v - mn) / (mx - mn));
    let s = `<svg viewBox="0 0 ${L} ${H}" width="100%" role="img" aria-label="${esc(opc.titulo || "gráfico")}">`;
    for (let k = 0; k <= 4; k++) {
      const v = mn + (mx - mn) * k / 4;
      s += `<line x1="${m.e}" x2="${L - m.d}" y1="${y(v)}" y2="${y(v)}" stroke="var(--linha)"/>`;
      s += `<text x="${m.e - 6}" y="${y(v) + 4}" text-anchor="end">${esc(opc.fmt ? opc.fmt(v) : nf(v, 0))}</text>`;
    }
    if (datas.length) {
      [0, Math.floor((datas.length - 1) / 2), datas.length - 1].forEach(i =>
        s += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${esc(dataPt(datas[i]))}</text>`);
    }
    if (opc.faixa) {
      const f = opc.faixa.map((p, i) => p ? [i, p] : null).filter(Boolean);
      if (f.length) {
        const cima = f.map(([i, p]) => `${x(i)},${y(p[1])}`).join(" ");
        const baixo = f.slice().reverse().map(([i, p]) => `${x(i)},${y(p[0])}`).join(" ");
        s += `<polygon points="${cima} ${baixo}" fill="var(--macaco)" opacity="0.18"/>`;
      }
    }
    series.forEach(se => {
      const pts = se.valores.map((v, i) => v == null ? null : `${x(i)},${y(v)}`).filter(Boolean).join(" ");
      s += `<polyline points="${pts}" fill="none" stroke="${se.cor}" stroke-width="${se.grossura || 2}" ${se.tracejado ? 'stroke-dasharray="5 4"' : ""}/>`;
    });
    return s + "</svg>";
  }

  // ---------- ranking ----------
  let ordem = { campo: "pontuacao", desc: true };
  function ranking() {
    const ult = A.diario[0];
    const idx = P["S&P 500 (€)"];
    const campos = {
      pontuacao: p => p.indicadores.pontuacao, rendibilidade: p => p.indicadores.rendibilidade,
      valor: p => p.indicadores.valor, diferenca: p => p.indicadores.diferenca_indice,
      perda: p => p.indicadores.perda_maxima, custos: p => p.indicadores.custos,
    };
    const lista = A.participantes.slice().sort((a, b) => {
      const va = campos[ordem.campo](a), vb = campos[ordem.campo](b);
      if (va == null && vb == null) return a.nome.localeCompare(b.nome);
      if (va == null) return 1; if (vb == null) return -1;
      return ordem.desc ? vb - va : va - vb;
    });
    const agentes = lista.filter(p => p.tipo === "agente");
    const podio = agentes.slice(0, 3);
    const th = (c, t, n = true) => `<th class="${n ? "n" : ""}" data-c="${c}">${t}${ordem.campo === c ? (ordem.desc ? " ▾" : " ▴") : ""}</th>`;
    let h = `<h1>Ranking</h1><p class="sub">${A.datas.length} noites desde ${dataPt(A.datas[0])}. ` +
      (ult ? `No último dia: ${ult.compras} compras, ${ult.vendas} vendas; o S&P 500 variou <span class="${cls(ult.sp500_variacao)}">${pct(ult.sp500_variacao)}</span>.` : "") + `</p>`;
    if (A.arena && A.arena.modo === "ensaio") h += `<p class="aviso">Modo <strong>ensaio</strong>: estes resultados servem para testar o motor e serão apagados no arranque oficial (1 de março de 2027).</p>`;
    h += `<div class="grelha" style="margin:16px 0">` + podio.map((p, i) =>
      `<a class="cartao kpi" href="${link(p.nome)}" style="text-decoration:none;color:inherit">
        <div class="r">${i + 1}.º lugar · <span class="etq ${p.etiqueta === "mérito" ? "merito" : ""}">${esc(p.etiqueta)}</span></div>
        <div class="v">${bola(p.especie)}${esc(p.nome)}</div>
        <div class="${cls(p.indicadores.rendibilidade)}">${pct(p.indicadores.rendibilidade)} <span class="r">(índice ${pct(idx ? idx.indicadores.rendibilidade : null)})</span></div>
      </a>`).join("") + `</div>`;
    h += `<div class="cartao tabela-rolar"><table><thead><tr><th>#</th><th>Participante</th>
      ${th("pontuacao", "Pontuação")}${th("rendibilidade", "Rendibilidade")}${th("diferenca", "vs índice")}
      ${th("valor", "Valor")}<th class="n esconder-tel">Melhor que macacos</th>${th("perda", "Perda máx.")}${th("custos", "Custos")}</tr></thead><tbody>`;
    lista.forEach((p, i) => {
      const ind = p.indicadores;
      const c = p.tipo === "agente" ? "" : p.tipo === "macaco" ? "macaco" : "ref";
      h += `<tr class="clique ${c}" data-n="${esc(p.nome)}"><td>${i + 1}</td><td>${bola(p.especie)}${esc(p.nome)}
        <span class="r esconder-tel" style="color:var(--suave);font-size:12px">${esc(p.especie)}</span></td>
        <td class="n">${nf(ind.pontuacao)}</td><td class="n ${cls(ind.rendibilidade)}">${pct(ind.rendibilidade)}</td>
        <td class="n ${cls(ind.diferenca_indice)}">${pct(ind.diferenca_indice)}</td><td class="n">${eur(ind.valor)}</td>
        <td class="n esconder-tel">${ind.melhor_que_macacos == null ? "—" : pct(ind.melhor_que_macacos, 0, false)}</td>
        <td class="n">${pct(-ind.perda_maxima)}</td><td class="n">${eur(ind.custos)}</td></tr>`;
    });
    h += `</tbody></table></div>
      <p class="sub" style="margin-top:10px">Pontuação: rendibilidade a mais do que o índice por unidade de risco extra (com castigo se a perda máxima passar de 25%). Aparece ao fim de 20 dias. Clicar nos títulos para ordenar.</p>`;
    // gráfico geral
    const series = A.participantes.filter(p => p.tipo === "agente").map(p => ({ valores: p.serie, cor: CORES[p.especie], grossura: 1.2 }));
    if (idx) series.push({ valores: idx.serie, cor: "var(--texto)", grossura: 2.5, tracejado: true });
    h += `<h2>Valor das carteiras</h2><div class="cartao">${grafico(series, { datas: A.datas, faixa: A.faixa_macacos })}
      <div class="legenda">${Object.keys(A.especies || {}).map(e => `<span>${bola(e)}${esc(e)}</span>`).join("")}
      <span>- - S&P 500 (€)</span><span>▒ faixa dos macacos</span></div></div>`;
    app.innerHTML = h;
    app.querySelectorAll("th[data-c]").forEach(e => e.onclick = () => {
      const c = e.dataset.c; ordem = { campo: c, desc: ordem.campo === c ? !ordem.desc : c !== "perda" && c !== "custos" }; ranking();
    });
    app.querySelectorAll("tr.clique").forEach(e => e.onclick = () => location.hash = link(e.dataset.n));
  }

  // ---------- ficha ----------
  function ficha(nome) {
    const p = P[nome];
    if (!p) { app.innerHTML = `<p>Participante não encontrado.</p>`; return; }
    const ind = p.indicadores, idx = P["S&P 500 (€)"];
    const desc = (A.especies && A.especies[p.especie]) ? A.especies[p.especie].descricao :
      p.tipo === "macaco" ? `escolhe ao acaso, com a mesma gestão de ${p.copia_gestao_de}` : "referência";
    let h = `<p><a href="#/">← Ranking</a></p><h1>${bola(p.especie)}${esc(p.nome)}</h1>
      <p class="sub">${esc(p.especie)}: ${esc(desc)}. Nasceu a ${dataPt(p.nascido)}${p.pais ? ` · pais: ${esc(p.pais)}` : ""}.
      ${p.etiqueta ? `<span class="etq ${p.etiqueta === "mérito" ? "merito" : ""}">${esc(p.etiqueta)}</span>` : ""}</p>`;
    const k = (r, v, c = "") => `<div class="cartao kpi"><div class="r">${r}</div><div class="v ${c}">${v}</div></div>`;
    h += `<div class="grelha">` +
      k("Valor da carteira", eur(ind.valor)) +
      k("Rendibilidade desde o nascimento", pct(ind.rendibilidade), cls(ind.rendibilidade)) +
      k("Diferença para o índice", pct(ind.diferenca_indice), cls(ind.diferenca_indice)) +
      k("Pontuação", nf(ind.pontuacao)) +
      k("Volatilidade (anual)", pct(ind.volatilidade, 1, false)) +
      k("Perda máxima", pct(-ind.perda_maxima, 1)) +
      k("Custos pagos", eur(ind.custos)) +
      k("Dividendos recebidos", eur(ind.dividendos)) +
      k("Rotação (vezes/ano)", nf(ind.rotacao, 1)) +
      k("% de acertos", ind.acertos == null ? "—" : pct(ind.acertos, 0, false) + ` <span class="r">(${ind.operacoes_fechadas})</span>`) +
      k("Imposto estimado no ano", eur(ind.imposto_estimado)) +
      k("Melhor que os macacos", ind.melhor_que_macacos == null ? "—" : pct(ind.melhor_que_macacos, 0, false)) +
      `</div><p class="sub" style="margin-top:8px">Imposto: 28% sobre os ganhos realizados no ano, só indicativo (não é aconselhamento fiscal). O ranking é antes de impostos.</p>`;
    const series = [{ valores: p.serie, cor: CORES[p.especie] || "var(--destaque)", grossura: 2.5 }];
    if (idx && p.nome !== idx.nome) series.push({ valores: idx.serie, cor: "var(--texto)", grossura: 1.5, tracejado: true });
    h += `<h2>Valor desde o nascimento</h2><div class="cartao">${grafico(series, { datas: A.datas, faixa: A.faixa_macacos })}
      <div class="legenda"><span>— ${esc(p.nome)}</span><span>- - S&P 500 (€)</span><span>▒ faixa dos macacos</span></div></div>`;
    if (p.adn) {
      const a = p.adn;
      h += `<h2>ADN</h2><div class="cartao"><table class="adn"><tbody>`;
      if (p.tipo === "agente") {
        Object.entries(a.pesos).forEach(([s, w]) => {
          h += `<tr><td>${esc(A.sinais_nomes[s] || s)}${["noticias", "valor", "qualidade"].includes(s) ? ' <span class="etq">fase 2</span>' : ""}</td>
            <td class="n" style="width:60px">${w}%</td><td><div class="barra" style="width:${w * 2}%"></div></td></tr>`;
        });
      }
      h += `<tr><td>Nº de empresas na carteira</td><td class="n">${a.n_empresas}</td><td></td></tr>
        <tr><td>Peso máximo por empresa</td><td class="n">${nf(a.peso_maximo * 100, 0)}%</td><td></td></tr>
        <tr><td>Revê a carteira</td><td class="n">${a.revisao_dias}</td><td>dias de bolsa</td></tr>
        <tr><td>Só troca se a nova for melhor por</td><td class="n">${nf(a.limiar, 1)}</td><td>pontos</td></tr>
        <tr><td>Corta perdas a</td><td class="n">${a.corta_perdas ? "−" + nf(a.corta_perdas * 100, 0) + "%" : "não"}</td><td>desde a compra</td></tr>
        <tr><td>Fica em dinheiro quando o mercado cai abaixo da média de 200 dias</td><td class="n">${nf(a.travao * 100, 0)}%</td><td></td></tr>
        </tbody></table></div>`;
    }
    h += `<h2>Carteira atual</h2><div class="cartao tabela-rolar"><table><thead><tr><th>Empresa</th><th class="n">Ações</th>
      <th class="n">Valor</th><th class="n">Peso</th><th class="n">Ganho</th><th class="n esconder-tel">Desde</th></tr></thead><tbody>`;
    p.carteira.slice().sort((a, b) => b.valor_eur - a.valor_eur).forEach(c => {
      h += `<tr><td><strong>${esc(c.ticker)}</strong> <span style="color:var(--suave)">${esc(c.nome)}</span></td>
        <td class="n">${nf(c.acoes, 4)}</td><td class="n">${eur(c.valor_eur)}</td><td class="n">${pct(c.peso, 1, false)}</td>
        <td class="n ${cls(c.ganho)}">${pct(c.ganho, 1)}</td><td class="n esconder-tel">${dataPt(c.desde)}</td></tr>`;
    });
    h += `<tr><td>Dinheiro</td><td></td><td class="n">${eur(p.dinheiro)}</td><td class="n">${pct(p.dinheiro / (ind.valor || 1), 1, false)}</td><td></td><td class="esconder-tel"></td></tr></tbody></table></div>`;
    if (p.pendentes.length) {
      h += `<h2>Ordens para a próxima abertura</h2><div class="cartao">` + p.pendentes.map(o =>
        `<div class="dec"><div class="cab">${o.lado === "compra" ? "Comprar" : "Vender"} ${esc(o.ticker)} ${o.lado === "compra" ? "· " + eur(o.eur) : o.tudo ? "· tudo" : "· " + nf(o.acoes, 4) + " ações"}</div>
         <div class="txt">${esc(o.texto)}</div></div>`).join("") + `</div>`;
    }
    h += `<h2>Diário de decisões</h2><div class="cartao">`;
    const decs = p.decisoes.slice(0, 300);
    if (!decs.length) h += `<p class="sub">Sem operações.</p>`;
    decs.forEach(d => {
      const tit = d.tipo === "compra" ? `Comprou ${esc(d.ticker)} · ${eur(d.eur)}` :
        d.tipo === "venda" ? `Vendeu ${esc(d.ticker)} · ${eur(d.eur)}${d.ganho != null ? ` · <span class="${cls(d.ganho)}">${d.ganho > 0 ? "+" : ""}${eur(d.ganho)}</span>` : ""}` :
        d.tipo === "dividendo" ? `Dividendo ${esc(d.ticker)} · ${eur(d.eur)}` : d.tipo === "split" ? `Split ${esc(d.ticker)}` : `Cancelada ${esc(d.ticker)}`;
      const det = d.acoes != null ? ` <span style="color:var(--suave);font-weight:400">(${nf(d.acoes, 4)} ações a ${nf(d.preco_usd, 2)} $; custos ${eur(d.custos)})</span>` : "";
      h += `<div class="dec"><div class="cab">${dataPt(d.data)} · ${tit}${det}</div><div class="txt">${esc(d.texto)}</div></div>`;
    });
    if (p.decisoes.length > 300) h += `<p class="sub">… e mais ${p.decisoes.length - 300} anteriores.</p>`;
    app.innerHTML = h + `</div>`;
  }

  // ---------- diário ----------
  function diario(data) {
    if (!A.diario.length) { app.innerHTML = "<p>Ainda não há noites.</p>"; return; }
    const d = A.diario.find(x => x.data === data) || A.diario[0];
    let h = `<h1>Diário</h1><p class="sub">O pacote de cada noite: o que se executou à abertura, com custos e justificação.</p>
      <p><select id="dia">${A.diario.map(x => `<option ${x.data === d.data ? "selected" : ""} value="${x.data}">${dataPt(x.data)}</option>`).join("")}</select></p>`;
    h += `<div class="grelha">
      <div class="cartao kpi"><div class="r">Compras</div><div class="v">${d.compras}</div></div>
      <div class="cartao kpi"><div class="r">Vendas</div><div class="v">${d.vendas}</div></div>
      <div class="cartao kpi"><div class="r">Ordens para o dia seguinte</div><div class="v">${d.ordens_amanha}</div></div>
      <div class="cartao kpi"><div class="r">S&P 500 no dia</div><div class="v ${cls(d.sp500_variacao)}">${pct(d.sp500_variacao)}</div></div>
      <div class="cartao kpi"><div class="r">EUR/USD (BCE)</div><div class="v">${nf(d.eurusd, 4)}</div></div>
      <div class="cartao kpi"><div class="r">Mercado vs média 200 dias</div><div class="v">${d.acima_media ? "acima" : "abaixo"}</div></div></div>`;
    const exc = Object.entries(d.excluidas || {});
    h += `<h2>Verificação dos dados</h2><div class="cartao">${exc.length ? "Empresas postas de lado nesta noite: " +
      exc.map(([t, m]) => `<strong>${esc(t)}</strong> (${esc(m)})`).join(", ") : "Tudo verificado, nenhuma empresa posta de lado."}
      <p class="sub" style="margin:8px 0 0;font-size:12px;word-break:break-all">Impressões digitais: preços ${esc((d.impressoes.precos || "").slice(0, 16))}…,
      eventos ${esc((d.impressoes.eventos || "").slice(0, 16))}…, câmbio ${esc((d.impressoes.cambio || "").slice(0, 16))}… · motor ${esc(d.versao.motor)}, regras ${esc(d.versao.regras)}, código ${esc(d.versao.codigo)}</p></div>`;
    h += `<h2>Operações executadas à abertura</h2><div class="cartao">`;
    if (!d.movimentos.length) h += `<p class="sub">Nenhuma operação neste dia.</p>`;
    d.movimentos.forEach(m => {
      h += `<div class="dec"><div class="cab"><a href="${link(m.participante)}">${esc(m.participante)}</a> ·
        ${m.tipo === "compra" ? "comprou" : "vendeu"} ${esc(m.ticker)} · ${eur(m.eur)}
        <span style="color:var(--suave);font-weight:400">(${nf(m.acoes, 4)} ações a ${nf(m.preco_usd, 2)} $; custos ${eur(m.custos)})</span></div>
        <div class="txt">${esc(m.texto)}</div></div>`;
    });
    app.innerHTML = h + `</div>`;
    document.getElementById("dia").onchange = e => location.hash = `#/diario/${e.target.value}`;
  }

  // ---------- regras ----------
  function regras() {
    const r = A.regras || {};
    const c = r.custos || {};
    app.innerHTML = `<h1>Regras e método</h1>
      <div class="cartao"><ol>
      <li>Só dinheiro fictício: cada participante começa com ${eur(r.capital)}. Nunca há ordens reais.</li>
      <li>Universo: as empresas do S&P 100, lista congelada a ${dataPt(A.arena && A.arena.universo_congelado_em)}.</li>
      <li>Decide-se de noite com os dados até ao fecho; executa-se ao preço de <strong>abertura do dia seguinte</strong>.</li>
      <li>Custos: comissão 0 €, câmbio ${pct(c.cambio, 2, false)} sobre o valor convertido (taxa do BCE), derrapagem ${pct(c.derrapagem, 2, false)} por operação.</li>
      <li>Dividendos creditados na data ex, com retenção de ${pct(c.retencao_dividendos, 0, false)}. Splits aplicados no dia certo. Ações fracionadas.</li>
      <li>Só compras, sem alavancagem, máximo de 20% numa só empresa.</li>
      <li>Referências: S&P 500 com dividendos em euros, e partes iguais nas 100 empresas sem mexer.</li>
      <li>Macacos: 10 participantes que escolhem ao acaso, para medir quanto se consegue por sorte.</li>
      <li>Tudo fica registado; qualquer noite refaz-se e dá exatamente o mesmo.</li>
      </ol><p class="sub">Versão das regras: ${esc(r.versao)}.</p></div>`;
  }

  function rota() {
    const h = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
    const [a, b] = [h.split("/")[0], h.split("/").slice(1).join("/")];
    window.scrollTo(0, 0);
    if (a === "agente") ficha(b);
    else if (a === "diario") diario(b);
    else if (a === "regras") regras();
    else ranking();
  }
  window.addEventListener("hashchange", rota);
  rota();
})();
