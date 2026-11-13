"""Conferência independente das contas de um participante (para o critério "3 agentes batem à mão").

Não usa o código do motor: lê só os ficheiros brutos (preços, eventos, câmbio) e as operações do diário,
refaz cada conta com as regras escritas em regras.json, e compara com o valor que o motor gravou.
Grava um CSV (abre no Excel) com todas as contas passo a passo.
"""
import csv
import json
import math
from pathlib import Path

REGRAS = json.loads((Path(__file__).resolve().parent.parent / "regras" / "regras.json").read_text(encoding="utf-8"))
CAMBIO = REGRAS["custos"]["cambio"]
DERR = REGRAS["custos"]["derrapagem"]
RET = REGRAS["custos"]["retencao_dividendos"]


def _ler_csv(caminho):
    if not Path(caminho).exists():
        return []
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def conferir(arq, nome, saida=None):
    raiz = Path(arq.raiz)
    precos = {}
    for r in _ler_csv(raiz / "brutos" / "precos.csv"):
        precos[(r["data"], r["ticker"])] = (float(r["abertura"]), float(r["fecho"]))
    eventos = {}
    for r in _ler_csv(raiz / "brutos" / "eventos.csv"):
        eventos.setdefault(r["data"], []).append((r["ticker"], r["tipo"], float(r["valor"])))
    cambio = sorted((r["data"], float(r["eurusd"])) for r in _ler_csv(raiz / "brutos" / "cambio.csv"))

    def taxa(d):
        t = None
        for data, v in cambio:
            if data > d:
                break
            t = v
        return t

    ultimo_fecho = {}
    dias = sorted(p.stem for p in (raiz / "diario").glob("*/*.json"))
    dinheiro = None
    acoes = {}
    linhas = []
    max_dif = 0.0
    for d in dias:
        j = json.loads((raiz / "diario" / d[:4] / f"{d}.json").read_text(encoding="utf-8"))
        if nome not in j["valores"]:
            continue
        tx = taxa(d)
        if dinheiro is None:
            dinheiro = float(REGRAS["capital_inicial_eur"])
            linhas.append([d, "nascimento", "", "", "", "", "", "", round(dinheiro, 2), ""])
        else:
            # dividendos e splits com data ex = hoje
            for t, tipo, v in eventos.get(d, []):
                if t not in acoes:
                    continue
                if tipo == "split":
                    acoes[t] = round(acoes[t] * v, 6)
                    linhas.append([d, "split", t, acoes[t], v, "", "", "", round(dinheiro, 2), "ações × razão"])
                else:
                    eur = round(acoes[t] * v * (1 - RET) / tx * (1 - CAMBIO), 2)
                    dinheiro = round(dinheiro + eur, 2)
                    linhas.append([d, "dividendo", t, acoes[t], v, tx, "", eur, round(dinheiro, 2),
                                   "ações × dividendo × 0,85 ÷ câmbio × (1 − 0,15%)"])
            # operações à abertura (o diário diz o quê; aqui refaz-se o quanto)
            for ex in j["decisoes"][nome]["execucoes"]:
                t = ex["ticker"]
                motivo = ex.get("motivo", {}).get("causa")
                abertura = precos[(d, t)][0] if motivo != "saida_bolsa" else ex["preco_usd"]
                derr = 0.0 if ex.get("preco_efetivo_usd") == ex["preco_usd"] else DERR
                if ex["lado"] == "compra":
                    eur = ex["eur"]
                    n = math.floor((eur * (1 - CAMBIO) * tx) / (abertura * (1 + derr)) * 1e6 + 1e-9) / 1e6
                    acoes[t] = round(acoes.get(t, 0.0) + n, 6)
                    dinheiro = round(dinheiro - eur, 2)
                    nota = "ações = € × (1 − 0,15%) × câmbio ÷ (abertura × 1,0005)"
                    dif_acoes = abs(n - ex["acoes"])
                else:
                    n = ex["acoes"]
                    eur = round(n * abertura * (1 - derr) / tx * (1 - CAMBIO), 2)
                    acoes[t] = round(acoes.get(t, 0.0) - n, 6)
                    if acoes[t] <= 1e-9:
                        del acoes[t]
                    dinheiro = round(dinheiro + eur, 2)
                    nota = "€ = ações × abertura × 0,9995 ÷ câmbio × (1 − 0,15%)"
                    dif_acoes = abs(eur - ex["eur"])
                linhas.append([d, ex["lado"], t, n, abertura, tx, "", eur, round(dinheiro, 2), nota])
                max_dif = max(max_dif, dif_acoes if ex["lado"] == "compra" else 0.0, abs(eur - ex["eur"]))
        # avaliação ao fecho
        valor = dinheiro
        for t, n in acoes.items():
            pf = precos.get((d, t))
            if pf:
                ultimo_fecho[t] = pf[1]
            f = ultimo_fecho.get(t) or _ultimo(precos, t, d)
            valor += n * f / tx
        valor = round(valor, 2)
        motor = j["valores"][nome]
        dif = round(valor - motor, 2)
        max_dif = max(max_dif, abs(dif))
        linhas.append([d, "fecho", "", "", "", tx, motor, valor, round(dinheiro, 2),
                       "valor = dinheiro + Σ ações × fecho ÷ câmbio" + ("" if abs(dif) <= 0.05 else f"  <<< DIFERENÇA {dif}")])
    saida = Path(saida) if saida else raiz / "conferencias" / f"{nome}.csv"
    saida.parent.mkdir(parents=True, exist_ok=True)
    with open(saida, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["data", "o quê", "empresa", "ações", "preço/dividendo/razão (USD)", "EUR/USD",
                    "valor do motor (€)", "conta independente (€)", "dinheiro (€)", "como se calcula"])
        for l in linhas:
            w.writerow([str(x).replace(".", ",") if isinstance(x, float) else x for x in l])
    ok = max_dif <= 0.05
    return f"{nome}: {'bate certo' if ok else 'NÃO bate'} (maior diferença {max_dif:.2f} €) -> {saida}"


def _ultimo(precos, t, d):
    datas = sorted(data for (data, tk) in precos if tk == t and data <= d)
    return precos[(datas[-1], t)][1] if datas else 0.0
