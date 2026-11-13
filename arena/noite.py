"""A noite: buscar dados, verificar, executar, avaliar, decidir e escrever o diário.

processar_dia() é uma função pura: os mesmos dados guardados + o mesmo estado = o mesmo pacote.
"""
import copy
import os
import subprocess
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import config, fontes
from .agentes import decidir
from .arquivo import impressao_digital
from .mercado import aplicar_eventos, avaliar, executar_pendentes, novo_participante, vender
from .sinais import calcular, mercado_bom
from .verificar import verificar
from .vista import Vista


# --- versão do código ---------------------------------------------------------
def versao_codigo():
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha[:12]
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.PASTA_MOTOR, capture_output=True,
                             text=True, check=True).stdout.strip()[:12]
        sujo = subprocess.run(["git", "status", "--porcelain", "--", "arena", "regras"], cwd=config.PASTA_MOTOR,
                              capture_output=True, text=True).stdout.strip()
        return sha + ("+alterado" if sujo else "")
    except Exception:
        return "desconhecida"


# --- buscar dados ---------------------------------------------------------------
def buscar(arq, agora=None, historico_desde=None):
    """Acrescenta ao arquivo os dados novos. Devolve um resumo (só contagens)."""
    agora_utc = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    obtido = agora_utc.strftime("%Y-%m-%dT%H:%M:%S")
    fim = fontes.ultimo_dia_fechado(agora_utc)
    p = arq.ler("precos")
    if historico_desde:
        inicio = historico_desde
    elif len(p):
        inicio = (pd.Timestamp(p["data"].max()) - pd.Timedelta(days=10)).date().isoformat()
    else:
        raise RuntimeError("arquivo sem histórico: correr primeiro 'criar'")
    tickers = config.tickers_universo() + config.INDICES
    precos, eventos = fontes.yahoo(tickers, inicio, fim)
    n_p = arq.acrescentar("precos", precos, obtido)
    n_e = arq.acrescentar("eventos", eventos, obtido)
    c = arq.ler("cambio")
    ini_c = historico_desde or ((pd.Timestamp(c["data"].max()) - pd.Timedelta(days=10)).date().isoformat() if len(c) else inicio)
    cambio = fontes.bce(ini_c)
    cambio = cambio[cambio["data"] <= fim]
    n_c = arq.acrescentar("cambio", cambio, obtido)
    n_t = _amostra_tiingo(arq, fim, obtido)
    return {"ate": fim, "precos": n_p, "eventos": n_e, "cambio": n_c, "tiingo": n_t}


def _amostra_tiingo(arq, dia, obtido, n=5):
    if not os.environ.get("TIINGO_KEY"):
        return 0
    t = arq.ler("tiingo")
    if len(t) and (t["data"] == dia).any():
        return 0
    univ = sorted(config.tickers_universo())
    import hashlib
    sem = int(hashlib.sha256(dia.encode()).hexdigest()[:8], 16)
    amostra = [univ[(sem + i * 17) % len(univ)] for i in range(n)]
    linhas = []
    for tk in amostra:
        df = fontes.tiingo(tk, dia, dia)
        if df is not None and len(df):
            linhas.append({"data": dia, "ticker": tk, "fecho": float(df["fecho"].iloc[-1])})
    return arq.acrescentar("tiingo", pd.DataFrame(linhas), obtido) if linhas else 0


# --- dias por processar -----------------------------------------------------------
def dias_por_processar(arq, ate=None):
    cfg = arq.cfg
    p = arq.ler("precos")
    dias = sorted(p.loc[p["ticker"] == config.INDICE_PRECO, "data"].unique().tolist())
    feitos = arq.dias_no_diario()
    ultimo = feitos[-1] if feitos else None
    c = arq.ler("cambio")
    primeiro_cambio = c["data"].min() if len(c) else "9999"
    out = [d for d in dias if d >= cfg["dia_zero"] and (ultimo is None or d > ultimo) and d >= primeiro_cambio]
    if ate:
        out = [d for d in out if d <= ate]
    # Se faltarem muitas empresas num dia, os dados ainda estão incompletos: espera-se pela noite seguinte.
    univ = set(config.tickers_universo())
    contagem = p[p["data"].isin(out) & p["ticker"].isin(univ)].groupby("data")["ticker"].nunique()
    completos = []
    for d in out:
        if contagem.get(d, 0) < 0.9 * len(univ):
            break
        completos.append(d)
    return completos


def dia_anterior_no_diario(arq, dia):
    feitos = [d for d in arq.dias_no_diario() if d < dia]
    return feitos[-1] if feitos else None


# --- processar um dia -----------------------------------------------------------
def corte_atual(arq):
    """Até onde vão os dados obtidos (data e hora da última busca)."""
    return max((arq.ler(n)["obtido_em"].max() for n in ("precos", "eventos", "cambio", "tiingo")
                if len(arq.ler(n))), default="")


def processar_dia(arq, dia, estado_anterior, corte=None):
    corte = corte or corte_atual(arq)
    vista = Vista(arq, dia, corte)
    if not vista.e_dia_de_bolsa(dia):
        raise RuntimeError(f"{dia} não é dia de bolsa no arquivo")
    taxa = vista.taxa(dia)
    universo = config.tickers_universo()

    if estado_anterior is None:
        estado = {"data": dia, "participantes": {}, "sem_dados": {}, "saidas": {}}
        for p in config.POPULACAO["participantes"]:
            estado["participantes"][p["nome"]] = novo_participante(p, dia)
        impressao_anterior = None
    else:
        impressao_anterior = impressao_digital(estado_anterior)
        estado = copy.deepcopy(estado_anterior)
        estado["data"] = dia

    decisoes = {}
    eventos_dia = vista.eventos_do_dia(dia)
    for nome, part in estado["participantes"].items():
        d = {"eventos": [], "execucoes": [], "canceladas": []}
        if estado_anterior is not None:
            part["dias"] += 1
            d["eventos"] = aplicar_eventos(part, eventos_dia, taxa)
            d["execucoes"], d["canceladas"] = executar_pendentes(part, vista, dia, taxa)
        decisoes[nome] = d

    # Saídas da bolsa: N dias seguidos sem dados -> venda obrigatória ao último preço
    hoje = vista.tickers_do_dia(dia)
    limite = config.DADOS["dias_sem_dados_para_saida"]
    for t in universo:
        if t in estado["saidas"]:
            continue
        if t in hoje:
            estado["sem_dados"].pop(t, None)
            continue
        estado["sem_dados"][t] = estado["sem_dados"].get(t, 0) + 1
        if estado["sem_dados"][t] >= limite:
            estado["saidas"][t] = dia
            estado["sem_dados"].pop(t, None)
            preco = vista.ultimo_fecho(t)
            for nome, part in estado["participantes"].items():
                part["pendentes"] = [o for o in part["pendentes"] if o["ticker"] != t]
                if t in part["posicoes"] and preco:
                    r = vender(part, t, part["posicoes"][t]["acoes"], preco, taxa, dia)
                    if r:
                        r["motivo"] = {"causa": "saida_bolsa",
                                       "texto": f"Venda obrigatória: {t} sem cotação há {limite} dias de bolsa (saída da bolsa), ao último preço conhecido."}
                        decisoes[nome]["execucoes"].append(r)
    estado["sem_dados"] = dict(sorted(estado["sem_dados"].items()))

    valores = {n: avaliar(p, vista, dia, taxa) for n, p in estado["participantes"].items()}

    excluidas, conferidas = verificar(vista, universo, estado["saidas"])
    elegiveis = [t for t in universo if t not in estado["saidas"] and t not in excluidas]
    brutos, z = calcular(vista, elegiveis)
    bom, sp, media = mercado_bom(vista)

    for nome, part in estado["participantes"].items():
        part["pendentes"] = decidir(part, dia, vista, taxa, valores[nome], z, brutos, excluidas,
                                    estado["saidas"], bom)

    sinais_tab = {t: {"z": {s: float(z.loc[t, s]) for s in config.SINAIS[:8]},
                      "bruto": {s: (None if pd.isna(brutos.loc[t, s]) else float(brutos.loc[t, s]))
                                for s in config.SINAIS[:8]}}
                  for t in z.index}
    return {
        "data": dia,
        "modo": arq.cfg.get("modo", "ensaio"),
        "versao": {"motor": config.VERSAO_MOTOR, "regras": config.VERSAO_REGRAS, "codigo": versao_codigo()},
        "entradas": {"corte": corte, **vista.impressoes(), "estado_anterior": impressao_anterior},
        "mercado": {"eurusd": taxa, "sp500": sp, "sp500_media_200": media, "acima_da_media": bom},
        "verificacao": {"excluidas": excluidas, "tiingo": conferidas,
                        "empresas_com_sinais": int(len(z))},
        "sinais": sinais_tab,
        "decisoes": decisoes,
        "valores": valores,
        "estado": estado,
    }


def processar(arq, ate=None, ao_terminar=None):
    feitos = []
    for dia in dias_por_processar(arq, ate):
        ant = dia_anterior_no_diario(arq, dia)
        estado = arq.ler_diario(ant)["estado"] if ant else None
        pacote = processar_dia(arq, dia, estado)
        arq.gravar_diario(dia, pacote)
        feitos.append(dia)
        if ao_terminar:
            ao_terminar(dia, pacote)
    return feitos


# --- refazer uma noite -------------------------------------------------------------
def refazer(arq, dia):
    guardado = arq.ler_diario(dia)
    if guardado is None:
        raise RuntimeError(f"não há diário de {dia}")
    ant = dia_anterior_no_diario(arq, dia)
    estado = arq.ler_diario(ant)["estado"] if ant else None
    novo = processar_dia(arq, dia, estado, guardado["entradas"]["corte"])
    import json
    novo = json.loads(json.dumps(novo, ensure_ascii=False))
    a, b = dict(guardado), dict(novo)
    cod_a = a.pop("versao", {}).get("codigo")
    cod_b = b.pop("versao", {}).get("codigo")
    diferencas = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    return {"dia": dia, "igual": not diferencas, "diferencas": diferencas,
            "codigo_guardado": cod_a, "codigo_agora": cod_b}
