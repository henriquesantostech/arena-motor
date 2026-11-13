"""Comandos da Arena.  Uso:  python -m arena <comando> --arquivo <pasta do arquivo>

  criar      cria uma arena nova no arquivo (dia zero + histórico de preços para os sinais)
  buscar     acrescenta ao arquivo os dados novos (Yahoo, BCE, Tiingo)
  processar  processa os dias de bolsa em falta (sem ir buscar dados)
  noite      buscar + processar + site  (é o que corre no GitHub todas as noites)
  refazer    refaz uma noite e confirma que dá exatamente o mesmo
  site       gera o site a partir do diário
  conferir   contas de um participante, passo a passo, para conferir à mão
"""
import argparse
import random
import sys
import traceback
from datetime import datetime, timezone

import pandas as pd

from . import config
from .arquivo import Arquivo


def main(argv=None):
    ap = argparse.ArgumentParser(prog="arena", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["criar", "buscar", "processar", "noite", "refazer", "site", "conferir"])
    ap.add_argument("--arquivo", required=True, help="pasta do arquivo privado")
    ap.add_argument("--dia-zero", help="criar: último dia de bolsa antes do primeiro dia de negociação")
    ap.add_argument("--modo", default="ensaio", choices=["ensaio", "oficial"])
    ap.add_argument("--ate", help="processar: só até este dia")
    ap.add_argument("--data", help="refazer: dia a refazer")
    ap.add_argument("--ao-acaso", action="store_true", help="refazer: um dia ao acaso")
    ap.add_argument("--participante", help="conferir: nome do participante")
    ap.add_argument("--saida", help="conferir: ficheiro CSV de saída")
    ap.add_argument("--detalhe", action="store_true", help="mostra o erro completo (só no PC)")
    a = ap.parse_args(argv)
    arq = Arquivo(a.arquivo)
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    try:
        if a.comando == "criar":
            return criar(arq, a.dia_zero, a.modo)
        if a.comando == "buscar":
            from .noite import buscar
            r = buscar(arq)
            print(f"dados até {r['ate']}: {r['precos']} linhas de preços, {r['eventos']} eventos, {r['cambio']} câmbios, {r['tiingo']} conferências")
            return 0
        if a.comando == "processar":
            from .noite import processar
            dias = processar(arq, a.ate)
            print(f"{len(dias)} dias processados" + (f" ({dias[0]} a {dias[-1]})" if dias else ""))
            return 0
        if a.comando == "noite":
            return noite(arq, agora)
        if a.comando == "refazer":
            return refazer(arq, a.data, a.ao_acaso, agora)
        if a.comando == "site":
            from .site import gerar
            gerar(arq)
            print("site gerado")
            return 0
        if a.comando == "conferir":
            from .conferir import conferir
            print(conferir(arq, a.participante, a.saida))
            return 0
    except Exception as e:  # nos registos públicos só sai o tipo e a mensagem
        print(f"ERRO: {type(e).__name__}: {e}")
        if "--detalhe" in sys.argv:
            traceback.print_exc()
        try:
            arq.registar(f"{agora},{a.comando},,erro {type(e).__name__}")
        except Exception:
            pass
        return 1


def criar(arq, dia_zero, modo):
    if not dia_zero:
        raise SystemExit("falta --dia-zero")
    if (arq.raiz / "arena.json").exists():
        raise SystemExit("este arquivo já tem uma arena")
    from .noite import buscar
    arq.gravar_cfg({"nome": "Arena de Agentes", "modo": modo, "dia_zero": dia_zero,
                    "universo_congelado_em": config.UNIVERSO["congelado_em"],
                    "criada_em": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "nota": "Ensaio: resultados apagados no arranque oficial (guardados à parte)." if modo == "ensaio" else ""})
    desde = (pd.Timestamp(dia_zero) - pd.Timedelta(days=430)).date().isoformat()
    r = buscar(arq, historico_desde=desde)
    print(f"arena criada (dia zero {dia_zero}); histórico desde {desde}: {r['precos']} linhas de preços")
    return 0


def noite(arq, agora):
    from .noite import buscar, processar
    from .site import gerar
    r = buscar(arq)
    dias = processar(arq)
    gerar(arq)
    res = f"ok: dados até {r['ate']}, {len(dias)} noites processadas"
    if dias:
        ult = arq.ler_diario(dias[-1])
        n_ord = sum(len(p["pendentes"]) for p in ult["estado"]["participantes"].values())
        n_exc = len(ult["verificacao"]["excluidas"])
        res += f", última {dias[-1]}: {n_ord} ordens para amanhã, {n_exc} empresas postas de lado"
    print(res)
    arq.registar(f"{agora},noite,{len(dias)},ok")
    return 0


def refazer(arq, data, ao_acaso, agora):
    from .noite import refazer as refazer_dia
    dias = arq.dias_no_diario()
    if not dias:
        print("ainda não há noites para refazer")
        return 0
    if ao_acaso:
        data = random.Random(agora[:10]).choice(dias)
    r = refazer_dia(arq, data)
    if r["igual"]:
        print(f"refazer {r['dia']}: igual")
        arq.registar(f"{agora},refazer {r['dia']},1,igual")
        return 0
    nota = "" if r["codigo_guardado"] == r["codigo_agora"] else f" (código mudou: {r['codigo_guardado']} -> {r['codigo_agora']})"
    print(f"refazer {r['dia']}: DIFERENTE em {', '.join(r['diferencas'])}{nota}")
    arq.registar(f"{agora},refazer {r['dia']},1,diferente")
    return 1


if __name__ == "__main__":
    sys.exit(main())
