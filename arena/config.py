"""Regras e constantes do jogo, lidas de regras/*.json (públicas, no motor)."""
import json
from pathlib import Path

VERSAO_MOTOR = "1.0.0"

PASTA_MOTOR = Path(__file__).resolve().parent.parent
PASTA_REGRAS = PASTA_MOTOR / "regras"
PASTA_SITE_MODELO = PASTA_MOTOR / "site"


def _ler(nome):
    return json.loads((PASTA_REGRAS / nome).read_text(encoding="utf-8"))


REGRAS = _ler("regras.json")
UNIVERSO = _ler("universo.json")
POPULACAO = _ler("populacao.json")

VERSAO_REGRAS = REGRAS["versao"]
CAPITAL = float(REGRAS["capital_inicial_eur"])
CAMBIO = REGRAS["custos"]["cambio"]
DERRAPAGEM = REGRAS["custos"]["derrapagem"]
RETENCAO = REGRAS["custos"]["retencao_dividendos"]
CART = REGRAS["carteira"]
DADOS = REGRAS["dados"]
MEDIDAS = REGRAS["medidas"]
SINAIS = POPULACAO["sinais"]

# Índices (só para referência e para o "travão" de mercado)
INDICE_PRECO = "^GSPC"      # S&P 500 (preço)
INDICE_TOTAL = "^SP500TR"   # S&P 500 com dividendos reinvestidos
INDICES = [INDICE_PRECO, INDICE_TOTAL]


def tickers_universo():
    return [e["ticker"] for e in UNIVERSO["empresas"]]


def simbolo_yahoo(ticker):
    return ticker if ticker.startswith("^") else ticker.replace(".", "-")


NOMES = {e["ticker"]: e["nome"] for e in UNIVERSO["empresas"]}

NOMES_SINAIS = {
    "tend_1m": "tendência 1 mês",
    "tend_3m": "tendência 3 meses",
    "tend_6m": "tendência 6 meses",
    "tend_12m": "tendência 12 meses",
    "regresso_1s": "queda na última semana",
    "regresso_1m": "queda no último mês",
    "risco_baixo": "risco baixo",
    "perto_maximo": "perto do máximo do ano",
    "noticias": "notícias",
    "valor": "valor",
    "qualidade": "qualidade",
}
