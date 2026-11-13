"""Como cada participante decide, todas as noites (desenho 5.2 e 6.1).

Agentes: pontuam as empresas com os pesos do ADN. Macacos: a mesma gestão, mas pontuação ao acaso.
Referências: compram no primeiro dia e não mexem.
A justificação sai diretamente das contas.
"""
import hashlib

import numpy as np
import pandas as pd

from . import config
from .mercado import acoes_r, cent, valor_posicao
from .sinais import parcelas, pontuar


def num(x, casas=2):
    return f"{x:,.{casas}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def sinal_txt(x, casas=2):
    return ("+" if x >= 0 else "−") + num(abs(x), casas)


def pontuacao_acaso(nome, dia, tickers):
    semente = int(hashlib.sha256(f"{nome}|{dia}".encode()).hexdigest()[:16], 16)
    rng = np.random.default_rng(semente)
    return pd.Series(rng.standard_normal(len(tickers)).round(4), index=sorted(tickers)), semente


def decidir(part, dia, vista, taxa, valor, z, brutos, excluidas, saidas, bom):
    tipo = part["tipo"]
    if tipo == "indice":
        return _decidir_indice(part)
    if tipo == "partes_iguais":
        return _decidir_partes_iguais(part, z, excluidas, saidas)
    return _decidir_gestor(part, dia, vista, taxa, valor, z, brutos, excluidas, saidas, bom)


def _decidir_indice(part):
    if part["dias"] != 0:
        return []
    return [{"lado": "compra", "ticker": config.INDICE_TOTAL, "eur": part["dinheiro"], "derrapagem": False,
             "motivo": {"texto": "Referência: compra o S&P 500 com dividendos no primeiro dia e não mexe mais."}}]


def _decidir_partes_iguais(part, z, excluidas, saidas):
    if part["dias"] != 0:
        return []
    alvo = [t for t in config.tickers_universo() if t not in excluidas and t not in saidas]
    eur = cent(int(part["dinheiro"] / len(alvo) * 100) / 100)
    return [{"lado": "compra", "ticker": t, "eur": eur,
             "motivo": {"texto": f"Referência: partes iguais nas {len(alvo)} empresas, no primeiro dia, e não mexe mais."}}
            for t in alvo]


def _decidir_gestor(part, dia, vista, taxa, V, z, brutos, excluidas, saidas, bom):
    adn = part["adn"]
    macaco = part["tipo"] == "macaco"
    pos = part["posicoes"]
    precos = {t: vista.fecho(t, dia) for t in pos}
    valores = {t: valor_posicao(p, precos[t], taxa) if precos[t] else 0.0 for t, p in pos.items()}
    elegiveis = [t for t in z.index if t not in excluidas and t not in saidas]
    if macaco:
        pont, semente = pontuacao_acaso(part["nome"], dia, elegiveis)
    else:
        pont = pontuar(z.loc[elegiveis], adn["pesos"]) if elegiveis else pd.Series(dtype=float)
        semente = None
    ranking = sorted(elegiveis, key=lambda t: (-float(pont[t]), t))
    lugar = {t: i + 1 for i, t in enumerate(ranking)}
    n_eleg = len(ranking)
    ordens = []
    vendidas = set()

    def info(t):
        d = {"pontuacao": float(pont[t]) if t in pont.index else None, "lugar": lugar.get(t), "de": n_eleg}
        if not macaco and t in z.index:
            d["parcelas"] = parcelas(z, adn["pesos"], t)
            for pc in d["parcelas"]:
                b = brutos.loc[t, pc["sinal"]]
                pc["bruto"] = None if pd.isna(b) else round(float(b), 4)
        if macaco:
            d["semente"] = str(semente)
        return d

    def explica(t):
        i = info(t)
        if i["pontuacao"] is None:
            return "", i
        base = f"Pontuação {num(i['pontuacao'])} ({i['lugar']}.º de {i['de']})."
        if macaco:
            return base + " Escolha ao acaso (sorteio da noite).", i
        partes = "; ".join(f"{config.NOMES_SINAIS[p['sinal']]} {sinal_txt(p['z'])}" for p in i["parcelas"])
        return f"{base} Pesou mais: {partes}.", i

    def vender(t, acoes, tudo, texto, causa):
        e, i = explica(t)
        ordens.append({"lado": "venda", "ticker": t, "acoes": acoes_r(acoes), "tudo": tudo,
                       "motivo": {"causa": causa, "texto": f"{texto} {e}".strip(), **i}})
        vendidas.add(t)

    def comprar(t, eur, texto, causa):
        e, i = explica(t)
        ordens.append({"lado": "compra", "ticker": t, "eur": cent(eur),
                       "motivo": {"causa": causa, "texto": f"{texto} {e}".strip(), **i}})

    # 1. Corta perdas (todos os dias)
    stop = adn.get("corta_perdas")
    if stop:
        for t, p in sorted(pos.items()):
            if precos[t] is None or t in excluidas:
                continue
            medio = p["custo_eur"] / p["acoes"]
            atual = precos[t] / taxa
            perda = atual / medio - 1
            if perda <= -stop:
                vender(t, p["acoes"], True,
                       f"Corta perdas: {sinal_txt(perda * 100, 1)}% desde a compra (limite −{num(stop * 100, 0)}%).",
                       "corta_perdas")

    revisao = part["dias"] % adn["revisao_dias"] == 0
    pmax = min(adn["peso_maximo"], config.CART["peso_maximo_global"])
    banda = config.CART["banda_reequilibrio"]
    if revisao and n_eleg:
        N = adn["n_empresas"]
        carteira = [t for t in pos if t not in vendidas]
        trocas = {}
        candidatos = [t for t in ranking if t not in carteira and t not in vendidas]
        while len(carteira) < N and candidatos:
            carteira.append(candidatos.pop(0))
        while candidatos:
            moveis = [t for t in carteira if t in lugar]
            if not moveis:
                break
            pior = min(moveis, key=lambda t: (float(pont[t]), t))
            melhor = candidatos[0]
            if float(pont[melhor]) > float(pont[pior]) + adn["limiar"]:
                carteira.remove(pior)
                carteira.append(melhor)
                candidatos.pop(0)
                trocas[pior] = melhor
            else:
                break
        f = 1.0 if bom or not adn.get("travao") else 1.0 - adn["travao"]
        peso = min(f / N, pmax)
        alvo = V * peso
        travao_txt = "" if f == 1.0 else f" Travão ligado: o mercado está abaixo da média de 200 dias, investe só {num(f * 100, 0)}%."
        # Saídas
        for t in sorted(pos):
            if t in vendidas or t in carteira:
                continue
            novo = trocas.get(t)
            texto = (f"Saiu: caiu para {lugar[t]}.º; trocada por {novo} "
                     f"({num(float(pont[novo]))} contra {num(float(pont[t]))}, diferença acima do limiar de {num(adn['limiar'])})."
                     if novo else "Saiu da carteira.")
            vender(t, pos[t]["acoes"], True, texto, "troca")
        # Ajustes e entradas
        estimado = part["dinheiro"]
        for o in ordens:
            if o["lado"] == "venda":
                p_ = pos[o["ticker"]]
                estimado += valores.get(o["ticker"], 0.0) * (o["acoes"] / p_["acoes"]) * (1 - config.CAMBIO - config.DERRAPAGEM)
        compras = []
        for t in sorted(carteira, key=lambda t: (lugar.get(t, 10**6), t)):
            if t in excluidas or t not in lugar and t not in pos:
                continue
            atual = valores.get(t, 0.0)
            dif = alvo - atual
            if t not in pos:
                quem = [k for k, v in trocas.items() if v == t]
                if macaco:
                    texto = f"Entrou por sorteio{', no lugar de ' + quem[0] if quem else ''}."
                else:
                    texto = f"Entrou: substitui {quem[0]}." if quem else "Entrou: está entre as melhores."
                compras.append((t, alvo, texto + travao_txt, "entrada"))
            elif dif < -banda * V and precos.get(t):
                acoes = -dif / (precos[t] / taxa)
                vender(t, acoes, False,
                       f"Reduz para o peso-alvo de {num(peso * 100, 1)}% (estava em {num(atual / V * 100, 1)}%).{travao_txt}",
                       "reequilibrio")
                estimado += -dif * (1 - config.CAMBIO - config.DERRAPAGEM)
            elif dif > banda * V:
                compras.append((t, dif, f"Reforça até ao peso-alvo de {num(peso * 100, 1)}% (estava em {num(atual / V * 100, 1)}%).", "reequilibrio"))
        total = sum(c[1] for c in compras)
        fator = 1.0 if total <= estimado or total == 0 else max(estimado, 0) / total
        for t, eur, texto, causa in compras:
            eur = eur * fator
            if eur >= config.CART["ordem_minima_eur"]:
                comprar(t, eur, texto, causa)
    else:
        # Fora do dia de revisão: só se respeita o peso máximo
        for t, p in sorted(pos.items()):
            if t in vendidas or t in excluidas or not precos[t]:
                continue
            if valores[t] > (pmax + config.CART["folga_peso"]) * V:
                excesso = valores[t] - pmax * V
                vender(t, excesso / (precos[t] / taxa), False,
                       f"Peso máximo: estava em {num(valores[t] / V * 100, 1)}%, limite {num(pmax * 100, 0)}%.",
                       "peso_maximo")
    return ordens
