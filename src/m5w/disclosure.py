"""Controle de divulgação: nenhuma célula publicada de pessoas pode ter de 1 a 4 (limiar k = 5).

1. Supressão primária: célula com 1 a 4 pessoas fica vazia e marcada como suprimida.
2. Supressão secundária: se um grupo (indicador x UF) tem uma única célula suprimida e o total
   é publicado, a célula seria recuperada por subtração. Suprime-se também a menor célula
   positiva restante do grupo. Se não houver outra célula positiva, o total também é suprimido.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def alocar_proporcional(total: int, pesos: np.ndarray) -> np.ndarray:
    """Distribui um total inteiro entre células conforme os pesos (método do maior resto)."""
    pesos = np.asarray(pesos, dtype=float)
    if total <= 0 or pesos.sum() <= 0:
        return np.zeros(len(pesos), dtype=int)
    bruto = total * pesos / pesos.sum()
    base = np.floor(bruto).astype(int)
    resto = total - base.sum()
    ordem = np.argsort(-(bruto - base), kind="mergesort")
    base[ordem[:resto]] += 1
    return base


def suprimir(df: pd.DataFrame, grupo: list[str], valor: str = "pessoas", k: int = 5) -> pd.DataFrame:
    """Aplica supressão primária e secundária. Espera uma linha de total por grupo com celula == 'total'."""
    d = df.copy()
    d["suprimido"] = d[valor].between(1, k - 1)
    d["motivo"] = np.where(d.suprimido, "primaria", "")
    for _, g in d.groupby(grupo, sort=False):
        celulas = g[g.celula != "total"]
        total = g[g.celula == "total"]
        if celulas.suprimido.sum() == 1 and not total.suprimido.any():
            cand = celulas[~celulas.suprimido & (celulas[valor] > 0)]
            if len(cand):
                i = cand.sort_values([valor, "celula"]).index[0]
                d.loc[i, ["suprimido", "motivo"]] = [True, "secundaria"]
            else:
                d.loc[total.index, ["suprimido", "motivo"]] = [True, "secundaria"]
    d[valor] = d[valor].astype("Int64").mask(d.suprimido)
    return d
