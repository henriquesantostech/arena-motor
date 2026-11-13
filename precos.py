# Arena de Agentes - fase 0: primeiro programa
# Descarrega os precos diarios de algumas empresas do S&P 100 e mostra um grafico.
# Correr com:  .venv\Scripts\python.exe precos.py

# --- Pedaco 1: ferramentas que vamos usar --------------------------------
from pathlib import Path            # para trabalhar com pastas e ficheiros

import matplotlib.pyplot as plt     # para desenhar o grafico
import pandas as pd                 # para tabelas (como uma folha de Excel)
import yfinance as yf               # para ir buscar precos ao Yahoo Finance


# --- Pedaco 2: o que queremos ---------------------------------------------
EMPRESAS = ["AAPL", "MSFT", "JNJ", "KO", "JPM"]   # Apple, Microsoft, Johnson & Johnson, Coca-Cola, JPMorgan
INICIO = "2025-01-01"                              # desde quando
PASTA_DADOS = Path("dados")                        # onde guardamos a tabela
PASTA_GRAFICOS = Path("graficos")                  # onde guardamos a imagem


# --- Pedaco 3: buscar ao Yahoo (fonte principal) ---------------------------
def buscar_yahoo(empresas, inicio):
    """Devolve uma tabela: uma linha por dia, uma coluna por empresa (preco de fecho)."""
    dados = yf.download(empresas, start=inicio, auto_adjust=True, progress=False)
    return dados["Close"]


# --- Pedaco 4: verificar o que chegou --------------------------------------
# (A reserva, Tiingo, entra na fase 1. Por agora, se o Yahoo falhar, o programa
#  para com uma mensagem clara e tenta-se mais tarde.)
def buscar_precos(empresas, inicio):
    precos = buscar_yahoo(empresas, inicio).dropna(how="all")
    if precos.empty:
        raise SystemExit("O Yahoo nao devolveu dados. Tenta daqui a pouco.")
    em_falta = [e for e in empresas if precos[e].isna().all()]
    if em_falta:
        print(f"Aviso: sem dados para {em_falta}")
    print("Fonte: Yahoo Finance")
    return precos


# --- Pedaco 5: o programa propriamente dito -------------------------------
def main():
    precos = buscar_precos(EMPRESAS, INICIO)

    # 5a. Mostrar um resumo no ecra
    print(f"\n{len(precos)} dias, de {precos.index[0].date()} a {precos.index[-1].date()}")
    print("\nUltimos 5 dias (preco de fecho, em dolares):")
    print(precos.tail().round(2))

    # 5b. Guardar a tabela num ficheiro que abre no Excel
    PASTA_DADOS.mkdir(exist_ok=True)
    precos.round(4).to_csv(PASTA_DADOS / "precos.csv")

    # 5c. Grafico: todas as empresas comecam em 100, para comparar a evolucao
    base_100 = precos / precos.bfill().iloc[0] * 100
    base_100.plot(figsize=(10, 5), title="Evolucao desde o inicio (inicio = 100)")
    plt.ylabel("valor (inicio = 100)")
    plt.grid(alpha=0.3)
    PASTA_GRAFICOS.mkdir(exist_ok=True)
    plt.savefig(PASTA_GRAFICOS / "precos.png", dpi=120, bbox_inches="tight")
    print("\nTabela: dados/precos.csv   Grafico: graficos/precos.png")
    plt.show()


if __name__ == "__main__":
    main()
