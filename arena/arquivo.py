"""O arquivo privado: dados brutos (só se acrescenta, nunca se reescreve), diário e estado.

Estrutura:
  arena.json                 configuração desta arena (modo, dia zero)
  brutos/precos.csv          data,ticker,abertura,maximo,minimo,fecho,volume,obtido_em
  brutos/eventos.csv         data,ticker,tipo,valor,obtido_em   (dividendos e splits)
  brutos/cambio.csv          data,eurusd,obtido_em              (BCE)
  brutos/tiingo.csv          data,ticker,fecho,obtido_em        (amostra de conferência)
  diario/AAAA/AAAA-MM-DD.json   pacote de cada noite
  diario/registo.csv         quando correu cada noite e o resultado
  estado/valores.csv         data,participante,valor
  site/                      site privado (abre-se no PC)
"""
import hashlib
import json
from pathlib import Path

import pandas as pd

COLUNAS = {
    "precos": ["data", "ticker", "abertura", "maximo", "minimo", "fecho", "volume", "obtido_em"],
    "eventos": ["data", "ticker", "tipo", "valor", "obtido_em"],
    "cambio": ["data", "eurusd", "obtido_em"],
    "tiingo": ["data", "ticker", "fecho", "obtido_em"],
}
CHAVES = {
    "precos": ["data", "ticker"],
    "eventos": ["data", "ticker", "tipo"],
    "cambio": ["data"],
    "tiingo": ["data", "ticker"],
}
TEXTO = {"data": str, "ticker": str, "tipo": str, "obtido_em": str}


class Arquivo:
    def __init__(self, raiz):
        self.raiz = Path(raiz)
        self._cache = {}

    # --- configuração -----------------------------------------------------
    @property
    def cfg(self):
        return json.loads((self.raiz / "arena.json").read_text(encoding="utf-8"))

    def gravar_cfg(self, cfg):
        self.raiz.mkdir(parents=True, exist_ok=True)
        escrever_json(self.raiz / "arena.json", cfg)

    # --- dados brutos -----------------------------------------------------
    def caminho(self, nome):
        return self.raiz / "brutos" / f"{nome}.csv"

    def ler(self, nome):
        if nome in self._cache:
            return self._cache[nome]
        c = self.caminho(nome)
        if c.exists():
            df = pd.read_csv(c, dtype=TEXTO, keep_default_na=False, na_values=[""])
        else:
            df = pd.DataFrame(columns=COLUNAS[nome])
        self._cache[nome] = df
        return df

    def acrescentar(self, nome, novos, obtido_em):
        """Junta só as linhas novas (chave ainda não existente). Nunca altera as que já lá estão."""
        if novos is None or len(novos) == 0:
            return 0
        atual = self.ler(nome)
        novos = novos.copy()
        novos["obtido_em"] = obtido_em
        novos = novos[COLUNAS[nome]]
        chave = CHAVES[nome]
        ja = set(map(tuple, atual[chave].astype(str).values.tolist())) if len(atual) else set()
        mask = [tuple(map(str, r)) not in ja for r in novos[chave].values.tolist()]
        novos = novos[mask].drop_duplicates(subset=chave)
        if not len(novos):
            return 0
        tudo = pd.concat([atual, novos], ignore_index=True) if len(atual) else novos
        tudo = tudo.sort_values(chave, kind="mergesort").reset_index(drop=True)
        c = self.caminho(nome)
        c.parent.mkdir(parents=True, exist_ok=True)
        tudo.to_csv(c, index=False, lineterminator="\n")
        self._cache.pop(nome, None)
        return len(novos)

    # --- diário e estado ----------------------------------------------------
    def caminho_diario(self, dia):
        return self.raiz / "diario" / dia[:4] / f"{dia}.json"

    def ler_diario(self, dia):
        c = self.caminho_diario(dia)
        return json.loads(c.read_text(encoding="utf-8")) if c.exists() else None

    def dias_no_diario(self):
        return sorted(p.stem for p in (self.raiz / "diario").glob("*/*.json"))

    def gravar_diario(self, dia, pacote):
        escrever_json(self.caminho_diario(dia), pacote)

    def registar(self, linha):
        c = self.raiz / "diario" / "registo.csv"
        c.parent.mkdir(parents=True, exist_ok=True)
        novo = not c.exists()
        with open(c, "a", encoding="utf-8", newline="\n") as f:
            if novo:
                f.write("corrido_em,acao,dias,resultado\n")
            f.write(linha + "\n")


def escrever_json(caminho, obj):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json_canonico(obj, indent=1) + "\n", encoding="utf-8", newline="\n")


def json_canonico(obj, indent=None):
    return json.dumps(obj, ensure_ascii=False, indent=indent, sort_keys=False, allow_nan=False)


def impressao_digital(df_ou_obj):
    """Código SHA-256 do conteúdo. Se um número mudar, o código muda."""
    if isinstance(df_ou_obj, pd.DataFrame):
        texto = df_ou_obj.to_csv(index=False, lineterminator="\n", float_format="%.6f")
    else:
        texto = json_canonico(df_ou_obj)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
