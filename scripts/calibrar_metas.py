"""Fixa as metas sintéticas do quadro (rodado uma vez, na criação do projeto).

As metas precisam ter a mesma ordem de grandeza da resposta simulada, senão o alcance fica
sem sentido (0% ou 5.000%). Este script parte do valor VERDADEIRO de cada indicador por UF
(relatos sem erros e, para os indicadores principais, o gabarito de pessoas únicas), aplica um
fator aleatório com semente fixa (alcance esperado entre cerca de 60% e 135%) e arredonda.
O resultado é gravado no bloco `metas` de config/quadro.yaml, que passa a ser a referência fixa.

Uso: python scripts/calibrar_metas.py   (depois de `m5w generate`)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from m5w.config import Caminhos, carregar_quadro
from m5w.tempo import agregar_indicadores


def arredondar(v: float) -> int:
    if v < 100:
        return max(1, int(round(v)))
    casas = len(str(int(v))) - 2
    return int(round(v / 10**casas) * 10**casas)


def main() -> None:
    c = Caminhos()
    q = carregar_quadro(c)
    rel = pd.read_csv(c.sintetico / "relatos_sem_erros.csv")
    real = agregar_indicadores(rel, q, ["uf"])
    gab = pd.read_csv(c.sintetico / "gabarito_pessoas_unicas.csv").groupby(["setor", "uf"]).pessoas_unicas.sum()
    for setor in q.setores:
        ind = q.principal(setor)
        sel = real.indicador == ind
        real.loc[sel, "realizado"] = [gab.get((setor, uf), 0) for uf in real.loc[sel, "uf"]]
    rng = np.random.default_rng(7)
    real = real.sort_values(["indicador", "uf"])
    real["meta"] = [arredondar(v / rng.uniform(0.6, 1.35)) for v in real.realizado]

    linhas = ["metas:"]
    for ind, g in real.groupby("indicador"):
        pares = ", ".join(f"{uf}: {m}" for uf, m in zip(g.uf, g.meta))
        linhas.append(f"  {ind}: {{{pares}}}")
    arq = c.config / "quadro.yaml"
    texto = arq.read_text(encoding="utf-8")
    texto = texto[: texto.index("metas:")] + "\n".join(linhas) + "\n"
    arq.write_text(texto, encoding="utf-8")
    print(f"{len(real)} metas gravadas em {arq}")


if __name__ == "__main__":
    main()
