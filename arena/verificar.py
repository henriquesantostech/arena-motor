"""Verificação dos dados antes de decidir (desenho 3.3).

Se algo falhar para uma empresa, não se decide nada sobre ela nessa noite, e fica registado.
"""
from . import config


def verificar(vista, universo, saidas):
    dia = vista.dia
    excluidas = {}
    hoje = vista.tickers_do_dia(dia)
    tab = vista.fecho_ajustado()
    eventos = vista.eventos_do_dia(dia)
    com_evento = set(eventos["ticker"]) if len(eventos) else set()
    for t in universo:
        if t in saidas:
            continue
        if t not in hoje:
            excluidas[t] = "sem dados hoje"
            continue
        if t in tab.columns:
            s = tab[t].dropna()
            if len(s) >= 2 and s.index[-1] == dia:
                salto = s.iloc[-1] / s.iloc[-2] - 1
                if abs(salto) > config.DADOS["salto_suspeito"] and t not in com_evento:
                    excluidas[t] = f"salto de {salto:+.0%} sem evento"
    # Conferência com o Tiingo (amostra guardada pela busca dessa noite)
    conferidas = []
    for _, r in vista.tiingo.iterrows():
        f = vista.fecho(r["ticker"], dia)
        if f is None:
            continue
        dif = abs(float(r["fecho"]) / f - 1)
        conferidas.append({"ticker": r["ticker"], "diferenca": round(dif, 5)})
        if dif > config.DADOS["diferenca_maxima_tiingo"]:
            excluidas[r["ticker"]] = f"Yahoo e Tiingo diferem {dif:.1%}"
    return dict(sorted(excluidas.items())), conferidas
