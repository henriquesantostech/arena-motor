"""Ir buscar dados às fontes grátis: Yahoo (preços e eventos), BCE (câmbio), Tiingo (conferência e reserva).

Nada daqui é escrito no motor público: tudo vai para o arquivo privado.
"""
import io
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from . import config

NY = ZoneInfo("America/New_York")
UA = {"User-Agent": "arena-de-agentes/1.0 (experiencia com dinheiro ficticio)"}


def ultimo_dia_fechado(agora=None):
    """Último dia cujo fecho já é definitivo: a partir das 18:00 de Nova Iorque."""
    agora = (agora or datetime.now(tz=NY)).astimezone(NY)
    dia = agora.date()
    if agora.time() < time(18, 0):
        dia -= timedelta(days=1)
    return dia.isoformat()


def yahoo(tickers, inicio, fim_incl, lote=20, tentativas=4):
    """Preços diários reais (não ajustados a dividendos) e eventos, em formato longo.

    Pede por lotes e repete as que falharem (a rede e o Yahoo falham de vez em quando).
    """
    import logging
    import time as _time

    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    faltam = list(tickers)
    precos, eventos = [], []
    for tentativa in range(tentativas):
        if not faltam:
            break
        if tentativa:
            _time.sleep(5 * tentativa)
        tam = lote if tentativa == 0 else max(1, lote // (2 * tentativa))
        recebidas = set()
        for i in range(0, len(faltam), tam):
            p, e = _yahoo_lote(faltam[i:i + tam], inicio, fim_incl)
            if len(p):
                precos.append(p)
                recebidas |= set(p["ticker"])
            if len(e):
                eventos.append(e)
        faltam = [t for t in faltam if t not in recebidas]
    p = pd.concat(precos, ignore_index=True) if precos else _vazio_precos()
    e = pd.concat(eventos, ignore_index=True) if eventos else _vazio_eventos()
    return p, e


def _yahoo_lote(tickers, inicio, fim_incl):
    import yfinance as yf

    simbolos = {config.simbolo_yahoo(t): t for t in tickers}
    fim = (pd.Timestamp(fim_incl) + pd.Timedelta(days=1)).date().isoformat()
    try:
        d = yf.download(list(simbolos), start=inicio, end=fim, auto_adjust=False, actions=True,
                        progress=False, group_by="column", threads=False, timeout=30, multi_level_index=True)
    except Exception:
        return _vazio_precos(), _vazio_eventos()
    precos, eventos = [], []
    if d is None or d.empty:
        return _vazio_precos(), _vazio_eventos()
    for simb, t in simbolos.items():
        if ("Close", simb) not in d.columns:
            continue
        sub = pd.DataFrame({
            "abertura": d[("Open", simb)], "maximo": d[("High", simb)], "minimo": d[("Low", simb)],
            "fecho": d[("Close", simb)], "volume": d[("Volume", simb)],
        }).dropna(subset=["fecho", "abertura"])
        sub = sub[(sub["fecho"] > 0) & (sub["abertura"] > 0)]
        sub.insert(0, "ticker", t)
        sub.insert(0, "data", [x.date().isoformat() for x in sub.index])
        precos.append(sub.reset_index(drop=True))
        for col, tipo in (("Dividends", "dividendo"), ("Stock Splits", "split")):
            if (col, simb) in d.columns:
                s = d[(col, simb)].dropna()
                s = s[s > 0]
                for x, v in s.items():
                    eventos.append({"data": x.date().isoformat(), "ticker": t, "tipo": tipo, "valor": float(v)})
    p = pd.concat(precos, ignore_index=True) if precos else _vazio_precos()
    p = p[p["data"] <= fim_incl]
    e = pd.DataFrame(eventos, columns=_vazio_eventos().columns)
    e = e[e["data"] <= fim_incl] if len(e) else e
    for c in ["abertura", "maximo", "minimo", "fecho"]:
        p[c] = p[c].astype(float).round(4)
    p["volume"] = p["volume"].fillna(0).astype("int64")
    return p.reset_index(drop=True), e.reset_index(drop=True)


def bce(inicio):
    """Taxa de referência diária do BCE: dólares por 1 euro."""
    url = ("https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
           f"?startPeriod={inicio}&format=csvdata")
    import time as _time
    for tentativa in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            break
        except requests.RequestException:
            if tentativa == 3:
                raise
            _time.sleep(10 * (tentativa + 1))
    df = pd.read_csv(io.StringIO(r.text))
    df = df[["TIME_PERIOD", "OBS_VALUE"]].dropna()
    df.columns = ["data", "eurusd"]
    df["eurusd"] = df["eurusd"].astype(float).round(6)
    return df.reset_index(drop=True)


def tiingo(ticker, inicio, fim_incl, chave=None):
    """Preços diários do Tiingo (reserva). Precisa da chave grátis (TIINGO_KEY)."""
    chave = chave or os.environ.get("TIINGO_KEY")
    if not chave:
        return None
    url = f"https://api.tiingo.com/tiingo/daily/{config.simbolo_yahoo(ticker)}/prices"
    r = requests.get(url, params={"startDate": inicio, "endDate": fim_incl, "token": chave},
                     headers=UA, timeout=60)
    if r.status_code != 200:
        return None
    linhas = [{"data": x["date"][:10], "ticker": ticker, "abertura": x["open"], "fecho": x["close"],
               "dividendo": x.get("divCash", 0.0), "split": x.get("splitFactor", 1.0)} for x in r.json()]
    return pd.DataFrame(linhas)


def _vazio_precos():
    return pd.DataFrame(columns=["data", "ticker", "abertura", "maximo", "minimo", "fecho", "volume"])


def _vazio_eventos():
    return pd.DataFrame(columns=["data", "ticker", "tipo", "valor"])
