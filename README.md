# Arena de Agentes (motor)

Experiência com **dinheiro fictício**: 20 agentes autónomos, 10 "macacos" que escolhem ao acaso e 2 referências
competem no S&P 100 real, com 100.000 € fictícios cada. Tudo é transparente: cada decisão tem justificação,
e qualquer noite pode ser refeita e dá exatamente o mesmo.

**Nada aqui é recomendação de investimento. Não há ligação a corretoras nem ordens reais.**

Este repositório (público) tem só o código e as regras do jogo. Os dados descarregados das fontes e os
resultados ficam num arquivo privado, porque os termos das fontes não permitem republicá-los.

## Como funciona uma noite

Corre sozinho no GitHub, de terça a sábado às 02:00 (UTC), depois do fecho da bolsa de Nova Iorque:

1. **Buscar**: preços diários e eventos (dividendos, splits) do Yahoo; câmbio EUR/USD do BCE; amostra do Tiingo para conferir.
   Os dados só se acrescentam ao arquivo, nunca se reescrevem.
2. **Verificar**: empresas sem dados ou com saltos de preço estranhos ficam de fora dessa noite.
3. **Executar** à abertura de hoje as ordens decididas ontem, com custos (câmbio 0,15% + derrapagem 0,05%).
   Antes disso aplicam-se os dividendos (com retenção de 15%) e os splits.
4. **Avaliar** cada carteira ao fecho.
5. **Sinais**: tendência (1, 3, 6 e 12 meses), regresso à média (semana, mês) e risco (volatilidade, distância ao máximo).
6. **Decidir**: cada agente pontua as empresas com os pesos do seu ADN e decide o que comprar e vender amanhã.
7. **Diário**: um pacote por noite com as impressões digitais dos dados, sinais, decisões, justificações e carteiras.
8. **Site**: ranking, fichas e diário, gerados a partir do diário.

## As peças

| Ficheiro | O que faz |
|---|---|
| `regras/regras.json` | custos, limites e medidas (as regras do jogo) |
| `regras/universo.json` | as 101 ações do S&P 100, lista congelada com data |
| `regras/populacao.json` | o ADN dos 20 agentes, os 10 macacos e as 2 referências |
| `regras/mudancas.md` | qualquer mudança às regras, com data e motivo |
| `arena/fontes.py` | ir buscar dados (Yahoo, BCE, Tiingo) |
| `arena/arquivo.py` | ler e acrescentar ao arquivo privado; impressões digitais |
| `arena/vista.py` | o que se sabia no fim de cada dia (nada do futuro entra) |
| `arena/verificar.py` | verificação dos dados |
| `arena/sinais.py` | sinais de preços |
| `arena/mercado.py` | o árbitro: execução, custos, dividendos, splits |
| `arena/agentes.py` | como cada participante decide e justifica |
| `arena/noite.py` | a noite inteira; refazer uma noite |
| `arena/medidas.py` | indicadores e pontuação do ranking |
| `arena/site.py` + `site/` | o site 2D |
| `arena/conferir.py` | conferência independente das contas de um participante (CSV para Excel) |
| `tests/` | testes com dados inventados |
| `.github/workflows/` | corrida noturna e testes |

## Comandos (PowerShell, na pasta do projeto)

```
.venv\Scripts\python.exe -m arena noite     --arquivo ..\arena-arquivo
.venv\Scripts\python.exe -m arena refazer   --arquivo ..\arena-arquivo --data 2026-11-20
.venv\Scripts\python.exe -m arena conferir  --arquivo ..\arena-arquivo --participante Flecha-01
.venv\Scripts\python.exe -m arena site      --arquivo ..\arena-arquivo
.venv\Scripts\python.exe -m pytest -q
```

Para ver o site com os resultados da última noite: `.\ver_site.ps1` (atualiza o arquivo e abre o site).

## Instalar o ambiente

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

A pasta `fase0` guarda o primeiro programa (gráfico de preços); precisa também de `matplotlib`.
