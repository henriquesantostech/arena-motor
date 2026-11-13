"""Sinais de preços, calculados todas as noites para cada empresa.

Cada sinal é convertido para a mesma escala (z: 0 = normal face às outras; limitado a -3..+3).
"""
import numpy as np
import pandas as pd

from . import config

DIAS = {"1s": 5, "1m": 21, "3m": 63, "6m": 126, "12m": 252}


def calcular(vista, elegiveis):
    """Devolve (brutos, z): DataFrames empresa × sinal. Só empresas elegíveis com histórico suficiente."""
    tab = vista.fecho_ajustado()
    hist_min = config.DADOS["historico_minimo_dias"]
    tab = tab.iloc[-(hist_min + 10):]
    cols = [t for t in elegiveis if t in tab.columns]
    tab = tab[cols]
    ok = [t for t in cols if tab[t].iloc[-hist_min:].notna().sum() >= hist_min - 5 and pd.notna(tab[t].iloc[-1])]
    tab = tab[ok].ffill()
    ult = tab.iloc[-1]

    def ret(n, salto=0):
        a = tab.iloc[-1 - salto]
        b = tab.iloc[-1 - n]
        return a / b - 1

    diarios = (tab / tab.shift(1) - 1).iloc[-63:]
    brutos = pd.DataFrame({
        "tend_1m": ret(21),
        "tend_3m": ret(63),
        "tend_6m": ret(126),
        "tend_12m": ret(252, salto=21),
        "regresso_1s": -ret(5),
        "regresso_1m": -ret(21),
        "risco_baixo": -diarios.std(ddof=0) * np.sqrt(252),
        "perto_maximo": ult / tab.iloc[-252:].max() - 1,
    })
    brutos = brutos.round(6)
    z = (brutos - brutos.mean()) / brutos.std(ddof=0)
    z = z.clip(-3, 3).fillna(0.0).round(4)
    for s in config.SINAIS:
        if s not in z.columns:
            z[s] = 0.0
            brutos[s] = np.nan
    z = z[config.SINAIS].sort_index()
    brutos = brutos[config.SINAIS].sort_index()
    return brutos, z


def pontuar(z, pesos):
    """Pontuação = soma dos sinais × pesos do ADN (pesos em %)."""
    w = pd.Series({s: pesos.get(s, 0) / 100 for s in config.SINAIS})
    return (z[config.SINAIS] * w).sum(axis=1).round(4)


def parcelas(z, pesos, ticker, n=3):
    """As n parcelas que mais pesaram na pontuação de uma empresa."""
    linha = z.loc[ticker]
    p = [(s, pesos.get(s, 0) / 100 * float(linha[s]), float(linha[s]), pesos.get(s, 0))
         for s in config.SINAIS if pesos.get(s, 0)]
    p.sort(key=lambda x: (-abs(x[1]), x[0]))
    return [{"sinal": s, "z": round(zv, 2), "peso": w, "parcela": round(v, 3)} for s, v, zv, w in p[:n]]


def mercado_bom(vista):
    """Travão: o S&P 500 está acima da média dos últimos 200 dias?"""
    p = vista.precos[vista.precos["ticker"] == config.INDICE_PRECO]["fecho"]
    n = config.DADOS["media_mercado_dias"]
    if len(p) < n:
        return True, None, None
    media = float(p.iloc[-n:].mean())
    ult = float(p.iloc[-1])
    return ult >= media, round(ult, 2), round(media, 2)
