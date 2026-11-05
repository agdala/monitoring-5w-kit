"""Agregação no tempo segundo a regra de cada indicador.

- soma: fluxo mensal (pessoas novas, atividades). Soma os meses.
- maximo: estoque (pessoas abrigadas, unidades apoiadas). Soma os parceiros em cada mês e
  pega o pico do ano. Somar os meses contaria a mesma pessoa abrigada várias vezes.
- ultimo: acumulado no ano. Pega o último valor de cada série (parceiro x município) e soma as séries.
"""

from __future__ import annotations

import pandas as pd

SERIE = ["parceiro_id", "municipio_cod", "indicador"]


def agregar_no_tempo(rel: pd.DataFrame, regra: str, por: list[str], valor: str = "valor") -> pd.Series:
    """Agrega relatos de um indicador no ano. `por` são as dimensões do resultado (ex.: ["uf"])."""
    if regra == "soma":
        return rel.groupby(por)[valor].sum()
    if regra == "maximo":
        return rel.groupby([*por, "mes"])[valor].sum().groupby(level=por).max()
    if regra == "ultimo":
        ult = rel.sort_values("mes").groupby(SERIE, as_index=False).last()
        return ult.groupby(por)[valor].sum()
    raise ValueError(f"regra de agregação desconhecida: {regra}")


def agregar_indicadores(rel: pd.DataFrame, quadro, por: list[str]) -> pd.DataFrame:
    """Aplica a regra de cada indicador do quadro. Devolve indicador x `por` com a coluna realizado."""
    partes = []
    for ind, g in rel.groupby("indicador"):
        if ind not in quadro.indicadores.index:
            continue
        regra = quadro.indicadores.at[ind, "agregacao_tempo"]
        s = agregar_no_tempo(g, regra, por).rename("realizado").reset_index()
        partes.append(s.assign(indicador=ind))
    return pd.concat(partes, ignore_index=True)[["indicador", *por, "realizado"]]
