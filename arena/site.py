"""Gera o site 2D (ranking, fichas, diário) a partir do diário.

O site é estático: index.html + app.js + estilo.css (do motor) e dados.js (gerado, só no arquivo privado).
Abre-se no PC com um duplo clique em site/index.html.
"""
import json
import shutil

from . import config
from .medidas import INDICE, etiqueta, indicadores


def gerar(arq):
    dias = arq.dias_no_diario()
    destino = arq.raiz / "site"
    destino.mkdir(parents=True, exist_ok=True)
    for f in config.PASTA_SITE_MODELO.glob("*"):
        if f.is_file():
            shutil.copyfile(f, destino / f.name)
    dados = construir(arq, dias)
    texto = "window.ARENA = " + json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (destino / "dados.js").write_text(texto, encoding="utf-8", newline="\n")
    return dados


def construir(arq, dias):
    cfg = arq.cfg
    if not dias:
        return {"arena": cfg, "datas": [], "participantes": [], "diario": []}
    series = {}
    decisoes = {}
    diario = []
    ultimo = None
    anterior_sp = None
    for d in dias:
        j = arq.ler_diario(d)
        ultimo = j
        compras = vendas = 0
        movimentos = []
        for nome, dec in j["decisoes"].items():
            for ex in dec["execucoes"]:
                compras += ex["lado"] == "compra"
                vendas += ex["lado"] == "venda"
                item = {"data": d, "tipo": ex["lado"], "ticker": ex["ticker"], "acoes": ex["acoes"],
                        "preco_usd": ex["preco_usd"], "eur": ex["eur"],
                        "custos": round(ex["custo_cambio_eur"] + ex["custo_derrapagem_eur"], 2),
                        "ganho": ex.get("ganho_eur"), "texto": ex.get("motivo", {}).get("texto", "")}
                decisoes.setdefault(nome, []).append(item)
                movimentos.append({"participante": nome, **item})
            for ev in dec["eventos"]:
                txt = (f"Dividendo de {ev['ticker']}: {ev['eur']:.2f} € (já com retenção de 15% e câmbio)".replace(".", ",")
                       if ev["tipo"] == "dividendo" else f"Split de {ev['ticker']}: ×{ev['razao']:g} ações")
                item = {"data": d, "tipo": ev["tipo"], "ticker": ev["ticker"], "eur": ev.get("eur"), "texto": txt}
                decisoes.setdefault(nome, []).append(item)
            for c in dec["canceladas"]:
                decisoes.setdefault(nome, []).append({"data": d, "tipo": "cancelada", "ticker": c["ticker"],
                                                      "texto": f"Ordem cancelada: {c['causa']}."})
        for nome, v in j["valores"].items():
            series.setdefault(nome, []).append((d, v))
        sp = j["mercado"]["sp500"]
        var = None if not (sp and anterior_sp) else round(sp / anterior_sp - 1, 6)
        anterior_sp = sp
        ordens = sum(len(p["pendentes"]) for p in j["estado"]["participantes"].values())
        diario.append({
            "data": d, "compras": compras, "vendas": vendas, "ordens_amanha": ordens,
            "sp500_variacao": var, "acima_media": j["mercado"]["acima_da_media"], "eurusd": j["mercado"]["eurusd"],
            "excluidas": j["verificacao"]["excluidas"], "movimentos": movimentos,
            "impressoes": j["entradas"], "versao": j["versao"],
        })

    estado = ultimo["estado"]
    hoje = ultimo["data"]
    ano = hoje[:4]
    serie_idx = series[INDICE]
    macacos = {n: series[n] for n, p in estado["participantes"].items() if p["tipo"] == "macaco"}
    participantes = []
    inds = {}
    for nome, p in estado["participantes"].items():
        inds[nome] = indicadores(nome, series[nome], serie_idx, p, macacos, ano)
    pont_macacos = [inds[n]["pontuacao"] for n in macacos]
    for nome, p in estado["participantes"].items():
        ind = inds[nome]
        carteira = []
        total = ind["valor"]
        for t, pos in sorted(p["posicoes"].items()):
            carteira.append({"ticker": t, "nome": config.NOMES.get(t, "S&P 500 com dividendos" if t == config.INDICE_TOTAL else t),
                             "acoes": pos["acoes"], "custo_eur": pos["custo_eur"], "desde": pos["desde"]})
        pend = [{"lado": o["lado"], "ticker": o["ticker"], "eur": o.get("eur"), "acoes": o.get("acoes"),
                 "tudo": o.get("tudo"), "texto": o["motivo"].get("texto", "")} for o in p["pendentes"]]
        participantes.append({
            "nome": nome, "tipo": p["tipo"], "especie": p["especie"], "nascido": p["nascido"],
            "pais": p.get("pais"), "copia_gestao_de": p.get("copia_gestao_de"), "adn": p["adn"],
            "dinheiro": p["dinheiro"], "carteira": carteira, "pendentes": pend,
            "indicadores": ind, "etiqueta": etiqueta(ind, pont_macacos) if p["tipo"] == "agente" else None,
            "serie": [v for _, v in series[nome]],
            "decisoes": list(reversed(decisoes.get(nome, []))),
        })
    # valor de cada posição ao último fecho (para a ficha): usa o diário do último dia
    _valorizar(arq, ultimo, participantes)
    faixa = []
    for i in range(len(dias)):
        vals = [series[n][i][1] for n in macacos if i < len(series[n])]
        faixa.append([min(vals), max(vals)] if vals else None)
    return {
        "arena": cfg, "atualizado": hoje, "datas": dias,
        "faixa_macacos": faixa, "participantes": participantes,
        "diario": list(reversed(diario)),
        "sinais_nomes": config.NOMES_SINAIS, "especies": config.POPULACAO["especies"],
        "regras": {"versao": config.VERSAO_REGRAS, "custos": config.REGRAS["custos"],
                   "capital": config.CAPITAL},
    }


def _valorizar(arq, ultimo, participantes):
    from .noite import Vista
    vista = Vista(arq, ultimo["data"], ultimo["entradas"]["corte"])
    taxa = ultimo["mercado"]["eurusd"]
    for p in participantes:
        tot = p["indicadores"]["valor"] or 1
        for c in p["carteira"]:
            preco = vista.fecho(c["ticker"], ultimo["data"]) or vista.ultimo_fecho(c["ticker"]) or 0
            c["valor_eur"] = round(c["acoes"] * preco / taxa, 2)
            c["peso"] = round(c["valor_eur"] / tot, 4)
            c["ganho"] = round(c["valor_eur"] / c["custo_eur"] - 1, 4) if c["custo_eur"] else None
