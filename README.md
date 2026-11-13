# Arena de Agentes (motor)

Experiência com **dinheiro fictício**: agentes autónomos que investem no S&P 100 real.
Nada aqui é recomendação de investimento nem há ligação a corretoras.

## Fase 0: o primeiro programa

`precos.py` descarrega os preços diários de 5 empresas do S&P 100 (Apple, Microsoft,
Johnson & Johnson, Coca-Cola, JPMorgan) desde 2025-01-01 e mostra um gráfico.

### Como correr (PowerShell)

```
cd <pasta do projeto>
.venv\Scripts\python.exe precos.py
```

Aparece no ecrã um resumo dos últimos 5 dias e abre-se uma janela com o gráfico.
Ficam também guardados:
- `dados\precos.csv` — a tabela de preços (abre no Excel);
- `graficos\precos.png` — a imagem do gráfico.

### As peças

| Peça | O que é |
|---|---|
| Python 3.14 | a linguagem; já estava instalada em `C:\Python314` |
| `.venv` | "ambiente virtual": uma cópia do Python só deste projeto, com as bibliotecas dele, para não misturar com outros |
| `requirements.txt` | a lista das bibliotecas e versões (yfinance, pandas, matplotlib) |
| `.gitignore` | o que nunca vai para o GitHub (ambiente, dados descarregados, gráficos) |

### O programa, pedaço a pedaço

1. **Ferramentas:** importa as bibliotecas. `yfinance` vai buscar os preços ao Yahoo; `pandas` trata tabelas; `matplotlib` desenha.
2. **O que queremos:** a lista de empresas (códigos da bolsa), a data de início e as pastas de saída. Para mudar de empresas, muda-se só aqui.
3. **Buscar ao Yahoo:** um único pedido para as 5 empresas; fica o preço de fecho já ajustado a dividendos e *splits*.
4. **Verificar:** se não veio nada, para com uma mensagem; se faltar alguma empresa, avisa.
5. **O programa:** mostra o resumo, grava a tabela e desenha o gráfico com todas a começar em 100, para se comparar a evolução e não o preço.

### Se precisar de reinstalar o ambiente

```
cd <pasta do projeto>
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```
