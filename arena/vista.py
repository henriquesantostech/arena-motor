"""O que se sabia no fim do dia D. Nada posterior a D entra aqui (regra de ouro 2)."""
import pandas as pd

from . import config
from .arquivo import impressao_digital

JANELA_DIAS_CORRIDOS = 420   # chega para 12 meses de bolsa + margem


class Vista:
    def __init__(self, arq, dia, corte):
        """corte: só entram linhas obtidas até esta data e hora (assim uma noite refeita usa os mesmos dados)."""
        self.dia = dia
        inicio = (pd.Timestamp(dia) - pd.Timedelta(days=JANELA_DIAS_CORRIDOS)).date().isoformat()

        def ate(nome):
            df = arq.ler(nome)
            return df[df["obtido_em"] <= corte]

        p = ate("precos")
        self.precos = p[(p["data"] <= dia) & (p["data"] >= inicio)].reset_index(drop=True)
        e = ate("eventos")
        self.eventos = e[e["data"] <= dia].reset_index(drop=True)
        c = ate("cambio")
        self.cambio = c[(c["data"] <= dia) & (c["data"] >= inicio)].reset_index(drop=True)
        t = ate("tiingo")
        self.tiingo = t[t["data"] == dia].reset_index(drop=True)

        idx = self.precos[self.precos["ticker"] == config.INDICE_PRECO]
        self.dias_bolsa = sorted(idx["data"].unique().tolist())
        self._por_dia = {d: g.set_index("ticker") for d, g in self.precos.groupby("data")}
        self._fecho_aj = None

    # --- impressões digitais das entradas ------------------------------------
    def impressoes(self):
        return {
            "precos": impressao_digital(self.precos),
            "eventos": impressao_digital(self.eventos),
            "cambio": impressao_digital(self.cambio),
            "tiingo": impressao_digital(self.tiingo),
        }

    # --- consultas -----------------------------------------------------------
    def e_dia_de_bolsa(self, d):
        return d in self._por_dia and config.INDICE_PRECO in self._por_dia[d].index

    def linha(self, ticker, d):
        g = self._por_dia.get(d)
        if g is None or ticker not in g.index:
            return None
        return g.loc[ticker]

    def abertura(self, ticker, d):
        r = self.linha(ticker, d)
        return None if r is None else float(r["abertura"])

    def fecho(self, ticker, d):
        r = self.linha(ticker, d)
        return None if r is None else float(r["fecho"])

    def ultimo_fecho(self, ticker):
        """Último fecho conhecido até D (para avaliar quando falta o dia)."""
        s = self.precos[self.precos["ticker"] == ticker]
        return None if s.empty else float(s["fecho"].iloc[-1])

    def taxa(self, d=None):
        d = d or self.dia
        c = self.cambio[self.cambio["data"] <= d]
        if c.empty:
            raise RuntimeError(f"sem taxa de câmbio do BCE até {d}")
        return float(c["eurusd"].iloc[-1])

    def eventos_do_dia(self, d):
        return self.eventos[self.eventos["data"] == d]

    def tickers_do_dia(self, d):
        g = self._por_dia.get(d)
        return set() if g is None else set(g.index)

    def fecho_ajustado(self):
        """Tabela dias × empresas com o fecho ajustado a splits (só para sinais e verificações).

        Uma linha obtida antes de um split ainda não vinha ajustada pelo Yahoo: divide-se pela razão.
        """
        if self._fecho_aj is not None:
            return self._fecho_aj
        p = self.precos[["data", "ticker", "fecho", "obtido_em"]].copy()
        splits = self.eventos[self.eventos["tipo"] == "split"]
        for _, s in splits.iterrows():
            m = (p["ticker"] == s["ticker"]) & (p["data"] < s["data"]) & (p["obtido_em"] < s["data"])
            p.loc[m, "fecho"] = p.loc[m, "fecho"] / float(s["valor"])
        tab = p.pivot(index="data", columns="ticker", values="fecho").sort_index()
        tab = tab.loc[[d for d in tab.index if d in set(self.dias_bolsa)]]
        self._fecho_aj = tab
        return tab
