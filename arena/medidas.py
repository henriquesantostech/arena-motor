"""Medir o sucesso (desenho cap. 7): indicadores da ficha e pontuação do ranking."""
import math

import numpy as np

from . import config

M = config.MEDIDAS
INDICE = "S&P 500 (€)"


def indicadores(nome, serie, serie_indice, part, series_macacos, ano):
    """serie: lista [(data, valor)] desde o nascimento."""
    datas = [d for d, _ in serie]
    v = np.array([x for _, x in serie], dtype=float)
    base = v[0]
    ret = v[-1] / base - 1
    idx = dict(serie_indice)
    vi = np.array([idx.get(d, np.nan) for d in datas], dtype=float)
    ret_idx = vi[-1] / vi[0] - 1 if len(vi) and vi[0] else None
    dias = len(v) - 1
    r = v[1:] / v[:-1] - 1 if dias else np.array([])
    ri = vi[1:] / vi[:-1] - 1 if dias else np.array([])
    vol = float(np.std(r, ddof=0) * math.sqrt(M["dias_por_ano"])) if dias > 1 else None
    pico = np.maximum.accumulate(v)
    perda_max = float(np.max(1 - v / pico)) if len(v) else 0.0
    ativo = r - ri
    ir = None
    if dias >= M["minimo_dias_pontuacao"] and np.std(ativo) > 0:
        ir = float(np.mean(ativo) / np.std(ativo, ddof=0) * math.sqrt(M["dias_por_ano"]))
    pont = None
    if ir is not None:
        castigo = max(0.0, perda_max - M["perda_maxima_castigo_a_partir"]) * M["castigo_por_ponto"]
        pont = ir - castigo
    a = part["acum"]
    media_v = float(np.mean(v))
    rotacao = (a["vendas_eur"] / media_v) * (M["dias_por_ano"] / dias) if dias and media_v else 0.0
    mv = a["mais_valias"].get(ano, 0.0)
    melhor_que = None
    if series_macacos and part["tipo"] != "macaco":
        rets = [s[-1][1] / s[0][1] - 1 for s in series_macacos.values() if s]
        melhor_que = sum(1 for x in rets if x < ret) / len(rets) if rets else None
    return {
        "valor": round(float(v[-1]), 2),
        "rendibilidade": round(ret, 6),
        "indice_mesmo_periodo": None if ret_idx is None else round(float(ret_idx), 6),
        "diferenca_indice": None if ret_idx is None else round(ret - float(ret_idx), 6),
        "volatilidade": None if vol is None else round(vol, 6),
        "perda_maxima": round(perda_max, 6),
        "custos": a["custos"],
        "dividendos": a["dividendos"],
        "rotacao": round(rotacao, 4),
        "acertos": None if not a["fechadas"] else round(a["ganhadoras"] / a["fechadas"], 4),
        "operacoes_fechadas": a["fechadas"],
        "imposto_estimado": round(max(0.0, mv) * M["imposto_mais_valias"], 2),
        "mais_valias_ano": mv,
        "pontuacao": None if pont is None else round(pont, 4),
        "melhor_que_macacos": None if melhor_que is None else round(melhor_que, 4),
        "dias": dias,
    }


def etiqueta(ind, pontuacoes_macacos):
    """Selo de mérito (desenho 6.4): 6 meses, bate o índice e pontuação acima de 95% dos macacos."""
    if ind["dias"] < M["merito_dias_minimos"]:
        return "provisório"
    if ind["diferenca_indice"] is None or ind["diferenca_indice"] <= 0 or ind["pontuacao"] is None:
        return "provisório"
    pm = [p for p in pontuacoes_macacos if p is not None]
    if not pm:
        return "provisório"
    acima = sum(1 for p in pm if p < ind["pontuacao"]) / len(pm)
    return "mérito" if acima >= M["merito_percentil_macacos"] else "provisório"
