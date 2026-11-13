"""O árbitro: executa as ordens à abertura, aplica custos, dividendos, splits e saídas da bolsa.

Conta em euros. Cada compra converte euros em dólares, cada venda converte dólares em euros:
  câmbio 0,15% sobre o valor convertido + derrapagem 0,05% sobre o preço.
"""
import math

from . import config

CASAS = config.CART["acoes_casas_decimais"]


def cent(x):
    return round(x + 0.0, 2)


def acoes_r(x):
    return round(x + 0.0, CASAS)


def acoes_baixo(x):
    f = 10 ** CASAS
    return math.floor(x * f + 1e-9) / f


def novo_participante(p, dia):
    return {
        "nome": p["nome"], "tipo": p["tipo"], "especie": p["especie"],
        "pais": p.get("pais"), "copia_gestao_de": p.get("copia_gestao_de"),
        "adn": p["adn"], "nascido": dia, "dias": 0,
        "dinheiro": config.CAPITAL, "posicoes": {}, "pendentes": [],
        "acum": {"custos": 0.0, "dividendos": 0.0, "compras_eur": 0.0, "vendas_eur": 0.0,
                 "fechadas": 0, "ganhadoras": 0, "mais_valias": {}},
    }


def _custo(part, eur):
    part["acum"]["custos"] = cent(part["acum"]["custos"] + eur)


def comprar(part, ticker, eur, preco_usd, taxa, dia, derrapagem=True):
    """Gasta `eur` euros. Devolve o registo da execução."""
    eur = cent(min(eur, part["dinheiro"]))
    if eur < config.CART["ordem_minima_eur"]:
        return None
    custo_cambio = eur * config.CAMBIO
    usd = (eur - custo_cambio) * taxa
    preco_ef = preco_usd * (1 + config.DERRAPAGEM) if derrapagem else preco_usd
    acoes = acoes_baixo(usd / preco_ef)
    if acoes <= 0:
        return None
    custo_derr = acoes * (preco_ef - preco_usd) / taxa
    part["dinheiro"] = cent(part["dinheiro"] - eur)
    pos = part["posicoes"].setdefault(ticker, {"acoes": 0.0, "custo_eur": 0.0, "desde": dia})
    pos["acoes"] = acoes_r(pos["acoes"] + acoes)
    pos["custo_eur"] = cent(pos["custo_eur"] + eur)
    _custo(part, custo_cambio + custo_derr)
    part["acum"]["compras_eur"] = cent(part["acum"]["compras_eur"] + eur)
    return {"lado": "compra", "ticker": ticker, "acoes": acoes, "preco_usd": preco_usd,
            "preco_efetivo_usd": round(preco_ef, 6), "eurusd": taxa, "eur": eur,
            "custo_cambio_eur": cent(custo_cambio), "custo_derrapagem_eur": cent(custo_derr)}


def vender(part, ticker, acoes, preco_usd, taxa, dia, derrapagem=True):
    pos = part["posicoes"].get(ticker)
    if not pos:
        return None
    acoes = acoes_r(min(acoes, pos["acoes"]))
    if acoes <= 0:
        return None
    preco_ef = preco_usd * (1 - config.DERRAPAGEM) if derrapagem else preco_usd
    usd = acoes * preco_ef
    eur_bruto = usd / taxa
    custo_cambio = eur_bruto * config.CAMBIO
    eur = cent(eur_bruto - custo_cambio)
    custo_derr = acoes * (preco_usd - preco_ef) / taxa
    fracao = acoes / pos["acoes"]
    custo_saida = cent(pos["custo_eur"] * fracao)
    ganho = cent(eur - custo_saida)
    part["dinheiro"] = cent(part["dinheiro"] + eur)
    _custo(part, custo_cambio + custo_derr)
    a = part["acum"]
    a["vendas_eur"] = cent(a["vendas_eur"] + eur)
    ano = dia[:4]
    a["mais_valias"][ano] = cent(a["mais_valias"].get(ano, 0.0) + ganho)
    total = acoes_r(pos["acoes"] - acoes)
    if total <= 0 or fracao > 0.999999:
        a["fechadas"] += 1
        custo_total_ganho = ganho  # ganho desta última venda
        if custo_total_ganho + pos.get("ganho_parcial", 0.0) > 0:
            a["ganhadoras"] += 1
        del part["posicoes"][ticker]
    else:
        pos["acoes"] = total
        pos["custo_eur"] = cent(pos["custo_eur"] - custo_saida)
        pos["ganho_parcial"] = cent(pos.get("ganho_parcial", 0.0) + ganho)
    return {"lado": "venda", "ticker": ticker, "acoes": acoes, "preco_usd": preco_usd,
            "preco_efetivo_usd": round(preco_ef, 6), "eurusd": taxa, "eur": eur,
            "custo_cambio_eur": cent(custo_cambio), "custo_derrapagem_eur": cent(custo_derr),
            "ganho_eur": ganho}


def aplicar_eventos(part, eventos, taxa):
    """Dividendos e splits com data ex = hoje, sobre a carteira antes das ordens de hoje."""
    feitos = []
    for _, ev in eventos.iterrows():
        t = ev["ticker"]
        pos = part["posicoes"].get(t)
        if not pos:
            continue
        v = float(ev["valor"])
        if ev["tipo"] == "split":
            antes = pos["acoes"]
            pos["acoes"] = acoes_r(antes * v)
            feitos.append({"tipo": "split", "ticker": t, "razao": v, "acoes_antes": antes,
                           "acoes_depois": pos["acoes"]})
        elif ev["tipo"] == "dividendo":
            usd_bruto = pos["acoes"] * v
            usd_liq = usd_bruto * (1 - config.RETENCAO)
            eur_bruto = usd_liq / taxa
            custo_cambio = eur_bruto * config.CAMBIO
            eur = cent(eur_bruto - custo_cambio)
            part["dinheiro"] = cent(part["dinheiro"] + eur)
            part["acum"]["dividendos"] = cent(part["acum"]["dividendos"] + eur)
            _custo(part, custo_cambio)
            feitos.append({"tipo": "dividendo", "ticker": t, "por_acao_usd": v, "acoes": pos["acoes"],
                           "retencao_usd": round(usd_bruto - usd_liq, 4), "eurusd": taxa, "eur": eur})
    return feitos


def executar_pendentes(part, vista, dia, taxa):
    """Ordens decididas na noite anterior, à abertura de hoje. Vendas primeiro, depois compras."""
    feitos, canceladas = [], []
    pend = part["pendentes"]
    part["pendentes"] = []
    for o in [o for o in pend if o["lado"] == "venda"]:
        preco = vista.abertura(o["ticker"], dia)
        if preco is None:
            canceladas.append({**o, "causa": "sem preço de abertura"})
            continue
        pos = part["posicoes"].get(o["ticker"])
        if not pos:
            canceladas.append({**o, "causa": "sem posição"})
            continue
        acoes = pos["acoes"] if o.get("tudo") else o["acoes"]
        r = vender(part, o["ticker"], acoes, preco, taxa, dia)
        if r:
            r["motivo"] = o["motivo"]
            feitos.append(r)
    compras = [o for o in pend if o["lado"] == "compra"]
    validas = []
    for o in compras:
        preco = vista.abertura(o["ticker"], dia)
        if preco is None:
            canceladas.append({**o, "causa": "sem preço de abertura"})
        else:
            validas.append((o, preco))
    total = sum(o["eur"] for o, _ in validas)
    fator = 1.0 if total <= part["dinheiro"] or total == 0 else part["dinheiro"] / total
    for o, preco in validas:
        eur = math.floor(o["eur"] * fator * 100) / 100
        r = comprar(part, o["ticker"], eur, preco, taxa, dia, derrapagem=o.get("derrapagem", True))
        if r:
            if fator < 1:
                r["reduzida"] = round(fator, 6)
            r["motivo"] = o["motivo"]
            feitos.append(r)
    return feitos, canceladas


def avaliar(part, vista, dia, taxa):
    """Valor da carteira ao fecho de D (ou último fecho conhecido)."""
    total = part["dinheiro"]
    for t, pos in part["posicoes"].items():
        preco = vista.fecho(t, dia)
        if preco is None:
            preco = vista.ultimo_fecho(t) or 0.0
        total += pos["acoes"] * preco / taxa
    return cent(total)


def valor_posicao(pos, preco_usd, taxa):
    return pos["acoes"] * preco_usd / taxa
