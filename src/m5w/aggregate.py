"""Etapa de agregação: realizado no ano, pessoas únicas (3 métodos x gabarito), metas e divulgação."""

from __future__ import annotations

import pandas as pd

from .config import CELULAS, Caminhos, atualizar_metricas, carregar_quadro
from .disclosure import alocar_proporcional, suprimir
from .tempo import SERIE, agregar_indicadores, agregar_no_tempo

METODOS = {
    "soma_simples": "Soma simples dos parceiros",
    "maximo_municipio": "Máximo por município e setor",
    "uniao_independente": "União sob independência (com PIN)",
}


# --------------------------------------------------------------------------------------------
# Pessoas únicas
# --------------------------------------------------------------------------------------------
def totais_por_parceiro(rel: pd.DataFrame, quadro) -> pd.DataFrame:
    """Pessoas novas no ano por parceiro, município e setor, a partir do indicador principal (regra soma)."""
    princ = quadro.indicadores[quadro.indicadores.principal]
    r = rel[rel.indicador.isin(princ.index)].assign(setor=lambda d: d.indicador.map(princ.setor))
    return r.groupby(["setor", "uf", "municipio_cod", "parceiro_id"], as_index=False).valor.sum()


def estimar_pessoas_unicas(tot: pd.DataFrame, pin: pd.DataFrame) -> pd.DataFrame:
    """Três estimativas de pessoas únicas por setor e UF.

    - soma_simples: soma de todos os parceiros (conta duas vezes quem foi atendido por dois).
    - maximo_municipio: em cada município e setor, só o maior parceiro (supõe sobreposição total).
    - uniao_independente: supõe que cada parceiro alcança uma amostra independente da população em
      necessidade (PIN) do município: únicos = PIN x (1 - prod(1 - n_i / PIN)).
    """
    t = tot.merge(pin[["municipio_cod", "setor", "pin"]], on=["municipio_cod", "setor"], how="left")
    t["frac_fora"] = 1 - (t.valor / t.pin).clip(upper=1)
    por_mun = t.groupby(["setor", "uf", "municipio_cod"]).agg(
        soma_simples=("valor", "sum"), maximo_municipio=("valor", "max"),
        prod_fora=("frac_fora", "prod"), pin=("pin", "first"))
    por_mun["uniao_independente"] = por_mun.pin * (1 - por_mun.prod_fora)
    sem_pin = por_mun.pin.isna()
    por_mun.loc[sem_pin, "uniao_independente"] = por_mun.loc[sem_pin, "maximo_municipio"]
    return por_mun.groupby(["setor", "uf"])[list(METODOS)].sum().round(0).astype(int).reset_index()


def comparar_com_gabarito(est: pd.DataFrame, gab: pd.DataFrame) -> pd.DataFrame:
    g = gab.groupby(["setor", "uf"], as_index=False).pessoas_unicas.sum().rename(columns={"pessoas_unicas": "gabarito"})
    d = g.merge(est, on=["setor", "uf"], how="left").fillna(0)
    for m in METODOS:
        d[f"erro_{m}_pct"] = (100 * (d[m] - d.gabarito) / d.gabarito).round(1)
    return d


def resumo_erros(comp: pd.DataFrame) -> dict:
    out = {}
    for m in METODOS:
        total = 100 * (comp[m].sum() - comp.gabarito.sum()) / comp.gabarito.sum()
        out[m] = {
            "erro_total_pct": round(float(total), 2),
            "erro_absoluto_medio_setor_uf_pct": round(float(comp[f"erro_{m}_pct"].abs().mean()), 2),
            "erro_por_setor_pct": {
                s: round(float(100 * (g[m].sum() - g.gabarito.sum()) / g.gabarito.sum()), 2)
                for s, g in comp.groupby("setor")
            },
        }
    return out


# --------------------------------------------------------------------------------------------
# Metas e realizado
# --------------------------------------------------------------------------------------------
def realizado_por_uf(rel: pd.DataFrame, quadro, est: pd.DataFrame) -> pd.DataFrame:
    real = agregar_indicadores(rel, quadro, ["uf"])
    oficial = est.assign(indicador=est.setor.map(quadro.principal))[["indicador", "uf", quadro.metodo_oficial]]
    oficial = oficial.rename(columns={quadro.metodo_oficial: "realizado"})
    principais = quadro.indicadores[quadro.indicadores.principal].index
    return pd.concat([real[~real.indicador.isin(principais)], oficial], ignore_index=True)


def metas_vs_realizado(real: pd.DataFrame, quadro) -> pd.DataFrame:
    ind = quadro.indicadores
    d = quadro.metas().merge(real, on=["indicador", "uf"], how="outer")
    d["meta"] = d.meta.astype("Int64")
    d["realizado"] = d.realizado.fillna(0).astype(int)
    d["alcance_pct"] = (100 * d.realizado / d.meta.astype(float)).round(1)
    d = d.join(ind[["setor", "setor_nome", "indicador_nome", "unidade", "agregacao_tempo"]], on="indicador")
    cols = ["setor", "setor_nome", "indicador", "indicador_nome", "unidade", "agregacao_tempo", "uf", "meta",
            "realizado", "alcance_pct"]
    return d[cols].sort_values(["setor", "indicador", "uf"]).reset_index(drop=True)


def alcance_por_indicador(mvr: pd.DataFrame) -> pd.DataFrame:
    d = mvr.dropna(subset=["meta"]).groupby(["setor", "setor_nome", "indicador", "indicador_nome", "unidade"],
                                            as_index=False)[["meta", "realizado"]].sum()
    d["alcance_pct"] = (100 * d.realizado / d.meta.astype(float)).round(1)
    return d


def alcance_pessoas_por_uf(mvr: pd.DataFrame, quadro) -> pd.DataFrame:
    """Alcance da meta de pessoas atendidas por UF: soma dos indicadores principais dos setores."""
    p = mvr[mvr.indicador.isin(quadro.indicadores[quadro.indicadores.principal].index)].dropna(subset=["meta"])
    d = p.groupby("uf", as_index=False)[["meta", "realizado"]].sum()
    d["alcance_pct"] = (100 * d.realizado / d.meta.astype(float)).round(1)
    return d


# --------------------------------------------------------------------------------------------
# Tabela desagregada publicada (com k = 5)
# --------------------------------------------------------------------------------------------
def celulas_no_ano(rel: pd.DataFrame, regra: str) -> pd.Series:
    """Células de sexo x faixa no ano, coerentes com a regra de agregação no tempo do indicador."""
    if regra == "soma":
        return rel[CELULAS].sum()
    if regra == "ultimo":
        return rel.sort_values("mes").groupby(SERIE).last()[CELULAS].sum()
    pico = rel.groupby("mes").valor.sum().idxmax()  # maximo: composição do mês de pico
    return rel[rel.mes == pico][CELULAS].sum()


def tabela_desagregada(rel: pd.DataFrame, real: pd.DataFrame, quadro) -> pd.DataFrame:
    ind = quadro.indicadores
    linhas = []
    pessoas = ind[(ind.unidade == "pessoas") & ind.desagregado].index
    for (cod, uf), g in rel[rel.indicador.isin(pessoas)].groupby(["indicador", "uf"]):
        cel = celulas_no_ano(g, ind.at[cod, "agregacao_tempo"]).to_numpy(dtype=float)
        total = int(real.loc[(real.indicador == cod) & (real.uf == uf), "realizado"].sum())
        valores = alocar_proporcional(total, cel) if ind.at[cod, "principal"] else cel.astype(int)
        total = int(valores.sum())
        for c, v in zip(CELULAS, valores):
            sexo, faixa = c.split("_", 1)
            linhas.append({"indicador": cod, "uf": uf, "celula": c, "sexo": sexo, "faixa_etaria": faixa,
                           "pessoas": int(v)})
        linhas.append({"indicador": cod, "uf": uf, "celula": "total", "sexo": "total", "faixa_etaria": "total",
                       "pessoas": total})
    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------------------------
def executar(caminhos: Caminhos | None = None) -> dict:
    c = caminhos or Caminhos()
    c.garantir()
    quadro = carregar_quadro(c)
    validos = pd.read_csv(c.reports / "relatos_validos.csv")
    limpos = pd.read_csv(c.sintetico / "relatos_sem_erros.csv")
    pin = pd.read_csv(c.sintetico / "pin.csv")
    gab = pd.read_csv(c.sintetico / "gabarito_pessoas_unicas.csv")

    comparacoes = {}
    for base, rel in (("relatos_validos", validos), ("relatos_sem_erros", limpos)):
        est = estimar_pessoas_unicas(totais_por_parceiro(rel, quadro), pin)
        comparacoes[base] = (est, comparar_com_gabarito(est, gab))
    est, comp = comparacoes["relatos_validos"]
    comp.to_csv(c.reports / "pessoas_unicas_metodos.csv", index=False)

    real = realizado_por_uf(validos, quadro, est)
    mvr = metas_vs_realizado(real, quadro)
    mvr.to_csv(c.reports / "metas_vs_realizado.csv", index=False)
    por_ind = alcance_por_indicador(mvr)
    por_ind.to_csv(c.reports / "alcance_por_indicador.csv", index=False)
    por_uf = alcance_pessoas_por_uf(mvr, quadro)
    por_uf.to_csv(c.reports / "alcance_pessoas_por_uf.csv", index=False)

    desag = suprimir(tabela_desagregada(validos, real, quadro), ["indicador", "uf"], k=quadro.limiar)
    desag.to_csv(c.publicacao / "pessoas_desagregadas_uf.csv", index=False)

    principais = por_ind[por_ind.indicador.isin(quadro.indicadores[quadro.indicadores.principal].index)]
    metricas = {
        "metodo_oficial_pessoas_unicas": quadro.metodo_oficial,
        "pessoas_unicas_gabarito": int(comp.gabarito.sum()),
        "pessoas_unicas_estimadas": {m: int(comp[m].sum()) for m in METODOS},
        "erro_metodos_relatos_validos": resumo_erros(comp),
        "erro_metodos_relatos_sem_erros": resumo_erros(comparacoes["relatos_sem_erros"][1]),
        "alcance_pessoas_por_setor_pct": {r.setor: float(r.alcance_pct) for r in principais.itertuples()},
        "alcance_por_indicador": {
            r.indicador: {"meta": int(r.meta), "realizado": int(r.realizado), "alcance_pct": float(r.alcance_pct)}
            for r in por_ind.itertuples()
        },
        "alcance_pessoas_por_uf_pct": {r.uf: float(r.alcance_pct) for r in por_uf.itertuples()},
        "metas_indicador_uf": int(mvr.meta.notna().sum()),
        "metas_atingidas": int((mvr.alcance_pct >= 100).sum()),
        "metas_abaixo_de_50_pct": int((mvr.alcance_pct < 50).sum()),
        "divulgacao": {
            "limiar_k": quadro.limiar,
            "celulas_publicadas": int(len(desag)),
            "suprimidas_primaria": int((desag.motivo == "primaria").sum()),
            "suprimidas_secundaria": int((desag.motivo == "secundaria").sum()),
            "celulas_de_1_a_4_publicadas": int(desag.pessoas.between(1, quadro.limiar - 1).sum()),
        },
        "soma_indevida_de_estoque": _ganho_soma_indevida(validos, quadro),
    }
    atualizar_metricas("agregacao", metricas, c)
    return metricas


def _ganho_soma_indevida(rel: pd.DataFrame, quadro) -> dict:
    """Quanto o total ficaria inflado se os indicadores de estoque/acumulado fossem somados mês a mês."""
    out = {}
    for cod, regra in quadro.indicadores.agregacao_tempo.items():
        if regra == "soma":
            continue
        g = rel[rel.indicador == cod]
        correto = float(agregar_no_tempo(g.assign(k=1), regra, ["k"]).sum())
        errado = float(g.valor.sum())
        out[cod] = {"regra": regra, "correto": int(correto), "somando_meses": int(errado),
                    "inflacao_pct": round(100 * (errado - correto) / correto, 1) if correto else None}
    return out

