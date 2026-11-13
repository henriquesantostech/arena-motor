"""Testes do motor com dados inventados (não precisam de internet).

Correr:  .venv\\Scripts\\python.exe -m pytest -q
"""
import json

import numpy as np
import pandas as pd
import pytest

from arena import config
from arena.arquivo import Arquivo
from arena.mercado import aplicar_eventos, comprar, novo_participante, vender
from arena.noite import processar, processar_dia, refazer

OBTIDO = "2026-01-01T00:00:00"


def criar_arquivo(raiz, n_dias=300, dia_zero_idx=270, ajustes=None):
    """Arquivo falso: passeio aleatório para as 101 empresas e os índices."""
    rng = np.random.default_rng(42)
    dias = pd.bdate_range("2025-01-02", periods=n_dias).strftime("%Y-%m-%d").tolist()
    linhas = []
    for t in config.tickers_universo() + config.INDICES:
        base = 7000.0 if t.startswith("^") else rng.uniform(20, 400)
        rets = rng.normal(0.0004, 0.015, n_dias)
        fechos = base * np.cumprod(1 + rets)
        aberturas = fechos * (1 + rng.normal(0, 0.003, n_dias))
        for d, a, f in zip(dias, aberturas, fechos):
            linhas.append({"data": d, "ticker": t, "abertura": round(a, 4), "maximo": round(max(a, f), 4),
                           "minimo": round(min(a, f), 4), "fecho": round(f, 4), "volume": 1000})
    precos = pd.DataFrame(linhas)
    eventos = pd.DataFrame(columns=["data", "ticker", "tipo", "valor"])
    if ajustes:
        precos, eventos = ajustes(precos, eventos, dias)
    cambio = pd.DataFrame({"data": dias, "eurusd": [1.10] * n_dias})
    arq = Arquivo(raiz)
    arq.gravar_cfg({"nome": "teste", "modo": "ensaio", "dia_zero": dias[dia_zero_idx], "universo_congelado_em": "x"})
    arq.acrescentar("precos", precos, OBTIDO)
    arq.acrescentar("eventos", eventos, OBTIDO)
    arq.acrescentar("cambio", cambio, OBTIDO)
    return arq, dias


# --- contas do árbitro --------------------------------------------------------------
def parte():
    return novo_participante({"nome": "X", "tipo": "agente", "especie": "t", "adn": None}, "2026-01-02")


def test_compra_com_custos():
    p = parte()
    r = comprar(p, "AAA", 10000.0, 100.0, 1.10, "2026-01-02")
    # 10 000 € - 0,15% = 9 985 € -> 10 983,50 $ ; preço com derrapagem 100,05 $
    assert r["acoes"] == pytest.approx(109.780109, abs=1e-6)
    assert p["dinheiro"] == 90000.0
    assert r["custo_cambio_eur"] == 15.0
    assert r["custo_derrapagem_eur"] == pytest.approx(109.780109 * 0.05 / 1.10, abs=0.01)


def test_venda_com_custos_e_mais_valia():
    p = parte()
    comprar(p, "AAA", 10000.0, 100.0, 1.10, "2026-01-02")
    acoes = p["posicoes"]["AAA"]["acoes"]
    r = vender(p, "AAA", acoes, 110.0, 1.10, "2026-02-02")
    esperado = round(acoes * 110.0 * 0.9995 / 1.10 * 0.9985, 2)
    assert r["eur"] == esperado
    assert r["ganho_eur"] == round(esperado - 10000.0, 2)
    assert "AAA" not in p["posicoes"]
    assert p["acum"]["fechadas"] == 1 and p["acum"]["ganhadoras"] == 1
    assert p["acum"]["mais_valias"]["2026"] == r["ganho_eur"]


def test_dividendo_com_retencao_e_split():
    p = parte()
    comprar(p, "AAA", 10000.0, 100.0, 1.10, "2026-01-02")
    acoes = p["posicoes"]["AAA"]["acoes"]
    dinheiro = p["dinheiro"]
    ev = pd.DataFrame([{"ticker": "AAA", "tipo": "dividendo", "valor": 1.0},
                       {"ticker": "BBB", "tipo": "dividendo", "valor": 5.0}])
    feitos = aplicar_eventos(p, ev, 1.10)
    assert len(feitos) == 1
    assert p["dinheiro"] == round(dinheiro + round(acoes * 1.0 * 0.85 / 1.10 * 0.9985, 2), 2)
    aplicar_eventos(p, pd.DataFrame([{"ticker": "AAA", "tipo": "split", "valor": 4.0}]), 1.10)
    assert p["posicoes"]["AAA"]["acoes"] == pytest.approx(acoes * 4, abs=1e-6)
    assert p["posicoes"]["AAA"]["custo_eur"] == 10000.0


# --- a noite inteira -------------------------------------------------------------------
def test_noites_reproduziveis(tmp_path):
    arq, dias = criar_arquivo(tmp_path / "a")
    feitos = processar(arq)
    assert feitos[0] == dias[270] and feitos[-1] == dias[-1]
    for d in (feitos[0], feitos[5], feitos[-1]):
        r = refazer(arq, d)
        assert r["igual"], r
    j = arq.ler_diario(feitos[-1])
    assert set(j["valores"]) == {p["nome"] for p in config.POPULACAO["participantes"]}
    # ninguém tem dinheiro negativo nem mais de 20% + folga numa empresa
    for nome, p in j["estado"]["participantes"].items():
        assert p["dinheiro"] >= 0, nome


def test_nao_ve_o_futuro(tmp_path):
    """Mudar preços depois de D não pode mudar nada da noite D."""
    arq1, dias = criar_arquivo(tmp_path / "a")
    processar(arq1, ate=dias[280])
    j1 = arq1.ler_diario(dias[280])

    def mexer_no_futuro(precos, eventos, dias_):
        m = precos["data"] > dias_[280]
        precos.loc[m, "fecho"] = precos.loc[m, "fecho"] * 3
        precos.loc[m, "abertura"] = precos.loc[m, "abertura"] * 0.2
        return precos, eventos

    arq2, _ = criar_arquivo(tmp_path / "b", ajustes=mexer_no_futuro)
    processar(arq2, ate=dias[280])
    j2 = arq2.ler_diario(dias[280])
    for k in ("valores", "sinais", "decisoes", "estado"):
        assert j1[k] == j2[k], k


def test_dados_chegados_depois_nao_mudam_noite_feita(tmp_path):
    """Uma linha que chega ao arquivo depois de a noite correr não entra quando se refaz essa noite."""
    arq, dias = criar_arquivo(tmp_path / "a")
    processar(arq, ate=dias[275])
    novos = pd.DataFrame([{"data": dias[275], "ticker": "ZZZ", "abertura": 1.0, "maximo": 1.0,
                           "minimo": 1.0, "fecho": 1.0, "volume": 1}])
    arq.acrescentar("precos", novos, "2027-01-01T00:00:00")
    assert refazer(arq, dias[275])["igual"]


def test_saida_da_bolsa_obriga_a_vender(tmp_path):
    def tirar_aapl(precos, eventos, dias_):
        return precos[~((precos["ticker"] == "AAPL") & (precos["data"] > dias_[272]))], eventos

    arq, dias = criar_arquivo(tmp_path / "a", ajustes=tirar_aapl)
    processar(arq)
    j = arq.ler_diario(dias[-1])
    assert "AAPL" in j["estado"]["saidas"]
    pi = j["estado"]["participantes"]["Partes iguais"]
    assert "AAPL" not in pi["posicoes"]
    saiu = arq.ler_diario(j["estado"]["saidas"]["AAPL"])
    vendas = [e for e in saiu["decisoes"]["Partes iguais"]["execucoes"] if e["ticker"] == "AAPL"]
    assert vendas and vendas[0]["motivo"]["causa"] == "saida_bolsa"


def test_split_nao_parece_queda(tmp_path):
    """Um split guardado depois dos preços antigos: os sinais ajustam e a verificação não exclui a empresa."""
    def split(precos, eventos, dias_):
        d = dias_[285]
        m = (precos["ticker"] == "MSFT") & (precos["data"] >= d)
        for c in ("abertura", "maximo", "minimo", "fecho"):
            precos.loc[m, c] = (precos.loc[m, c] / 4).round(4)
        eventos = pd.DataFrame([{"data": d, "ticker": "MSFT", "tipo": "split", "valor": 4.0}])
        return precos, eventos

    arq, dias = criar_arquivo(tmp_path / "a", ajustes=split)
    # simula a realidade: as linhas antigas foram obtidas antes do split
    p = arq.ler("precos").copy()
    p.loc[p["data"] >= dias[285], "obtido_em"] = dias[285] + "T23:00:00"
    p.to_csv(arq.caminho("precos"), index=False, lineterminator="\n")
    e = arq.ler("eventos").copy()
    e["obtido_em"] = dias[285] + "T23:00:00"
    e.to_csv(arq.caminho("eventos"), index=False, lineterminator="\n")
    arq._cache.clear()
    # comprar MSFT antes do split, via partes iguais
    processar(arq)
    j = arq.ler_diario(dias[285])
    assert "MSFT" not in j["verificacao"]["excluidas"]
    assert abs(j["sinais"]["MSFT"]["bruto"]["tend_1m"]) < 0.5
    antes = arq.ler_diario(dias[284])["estado"]["participantes"]["Partes iguais"]["posicoes"]["MSFT"]["acoes"]
    depois = j["estado"]["participantes"]["Partes iguais"]["posicoes"]["MSFT"]["acoes"]
    assert depois == pytest.approx(antes * 4, abs=1e-5)
    # o valor não salta com o split
    v = [arq.ler_diario(d)["valores"]["Partes iguais"] for d in (dias[284], dias[285])]
    assert abs(v[1] / v[0] - 1) < 0.05


def test_conferencia_independente(tmp_path):
    from arena.conferir import conferir
    arq, dias = criar_arquivo(tmp_path / "a")
    processar(arq)
    for nome in ("Flecha-01", "Onda-03", "Macaco-02", "Partes iguais", "S&P 500 (€)"):
        assert "bate certo" in conferir(arq, nome, tmp_path / f"{nome}.csv")


def test_site_gera(tmp_path):
    from arena.site import gerar
    arq, dias = criar_arquivo(tmp_path / "a")
    processar(arq)
    d = gerar(arq)
    assert len(d["participantes"]) == 32
    assert (tmp_path / "a" / "site" / "dados.js").exists()
    assert (tmp_path / "a" / "site" / "index.html").exists()
