"""Etapa de validação: aplica as regras, separa relatos válidos e gera as pendências por parceiro."""

from __future__ import annotations

import pandas as pd

from .config import Caminhos, atualizar_metricas, carregar_gerador, carregar_municipios, carregar_quadro
from .rules import REGRAS, aplicar_regras, preparar

PESOS_INDICE = {"validade": 0.50, "conformidade": 0.25, "pontualidade": 0.25}


def faixa(indice: float) -> str:
    return "A" if indice >= 95 else "B" if indice >= 85 else "C"


def indice_qualidade(rel: pd.DataFrame, achados: pd.DataFrame, parceiros: pd.DataFrame) -> pd.DataFrame:
    """Índice de 0 a 100 por parceiro.

    validade = % de relatos sem erro; conformidade = % sem alerta de variação atípica (V10);
    pontualidade = % enviados no prazo (sem V09). Índice = 50% validade + 25% conformidade + 25% pontualidade.
    """
    def relatos_com(mask: pd.Series) -> set:
        return set(achados.loc[mask, "relato_id"])

    com_erro = relatos_com(achados.severidade == "erro")
    atipico = relatos_com(achados.regra == "V10")
    atraso = relatos_com(achados.regra == "V09")
    d = rel[["relato_id", "parceiro_id"]].assign(
        erro=rel.relato_id.isin(com_erro), atipico=rel.relato_id.isin(atipico), atraso=rel.relato_id.isin(atraso))
    q = d.groupby("parceiro_id").agg(relatos=("relato_id", "size"), relatos_com_erro=("erro", "sum"),
                                     relatos_atipicos=("atipico", "sum"), relatos_fora_prazo=("atraso", "sum"))
    q["validade_pct"] = (100 * (1 - q.relatos_com_erro / q.relatos)).round(1)
    q["conformidade_pct"] = (100 * (1 - q.relatos_atipicos / q.relatos)).round(1)
    q["pontualidade_pct"] = (100 * (1 - q.relatos_fora_prazo / q.relatos)).round(1)
    q["indice_qualidade"] = sum(q[f"{k}_pct"] * w for k, w in PESOS_INDICE.items()).round(1)
    q["faixa"] = q.indice_qualidade.map(faixa)
    q = parceiros[["parceiro_nome"]].join(q, how="right")
    return q.sort_values(["indice_qualidade", "parceiro_id"]).reset_index()


def taxa_deteccao(rel: pd.DataFrame, achados: pd.DataFrame, erros: pd.DataFrame) -> pd.DataFrame:
    """Para cada tipo de erro injetado: quantos a regra correspondente detectou (recall) e quantos dos
    relatos sinalizados pela regra eram de fato daquele tipo (precisão)."""
    linhas = []
    for r in REGRAS:
        sinalizados = set(achados.loc[achados.regra == r.codigo, "relato_id"])
        injetados = set(erros.loc[erros.tipo_erro == r.tipo_injetado, "relato_id"]) if r.tipo_injetado else set()
        acertos = len(sinalizados & injetados)
        linhas.append({
            "regra": r.codigo, "regra_nome": r.nome, "severidade": r.severidade,
            "tipo_erro_injetado": r.tipo_injetado or "(não injetado)",
            "injetados": len(injetados), "detectados": acertos,
            "taxa_deteccao_pct": round(100 * acertos / len(injetados), 1) if injetados else None,
            "sinalizados": len(sinalizados),
            "precisao_pct": round(100 * acertos / len(sinalizados), 1) if (sinalizados and injetados) else None,
        })
    return pd.DataFrame(linhas)


def executar(caminhos: Caminhos | None = None) -> dict:
    c = caminhos or Caminhos()
    c.garantir()
    quadro = carregar_quadro(c)
    cfg = carregar_gerador(c)
    rel = pd.read_csv(c.sintetico / "relatos.csv")
    pin = pd.read_csv(c.sintetico / "pin.csv")
    parceiros = pd.read_csv(c.sintetico / "parceiros.csv").set_index("parceiro_id")
    erros = pd.read_csv(c.sintetico / "erros_injetados.csv")

    d = preparar(rel, quadro, carregar_municipios(c), pin, cfg["prazo_dia"])
    achados = aplicar_regras(d)

    bloqueados = set(achados.loc[achados.severidade == "erro", "relato_id"])
    alertas = achados[achados.severidade == "alerta"].groupby("relato_id").regra.agg(";".join)
    validos = rel[~rel.relato_id.isin(bloqueados)].copy()
    validos["alertas"] = validos.relato_id.map(alertas).fillna("")
    validos.to_csv(c.reports / "relatos_validos.csv", index=False)

    pend = achados.merge(rel[["relato_id", "parceiro_id", "parceiro_nome", "mes", "indicador", "municipio_cod"]],
                         on="relato_id")
    pend["ordem_sev"] = pend.severidade.map({"erro": 0, "alerta": 1})
    pend = pend.sort_values(["parceiro_id", "ordem_sev", "regra", "mes", "relato_id"]).drop(columns="ordem_sev")
    pend[["parceiro_id", "parceiro_nome", "relato_id", "mes", "indicador", "municipio_cod", "regra", "regra_nome",
          "severidade", "mensagem"]].to_csv(c.reports / "pendencias_por_parceiro.csv", index=False)

    qualidade = indice_qualidade(rel, achados, parceiros)
    qualidade.to_csv(c.reports / "qualidade_parceiros.csv", index=False)
    deteccao = taxa_deteccao(rel, achados, erros)
    deteccao.to_csv(c.reports / "deteccao_erros.csv", index=False)

    det = deteccao[deteccao.injetados > 0]
    metricas = {
        "relatos_recebidos": int(len(rel)),
        "relatos_validos": int(len(validos)),
        "relatos_bloqueados": int(len(bloqueados)),
        "pct_relatos_bloqueados": round(100 * len(bloqueados) / len(rel), 2),
        "relatos_com_alerta": int(validos.alertas.ne("").sum()),
        "pendencias": int(len(achados)),
        "sinalizacoes_por_regra": {k: int(v) for k, v in achados.regra.value_counts().sort_index().items()},
        "deteccao_por_regra": {
            r.regra: {"tipo": r.tipo_erro_injetado, "injetados": int(r.injetados), "detectados": int(r.detectados),
                      "taxa_deteccao_pct": float(r.taxa_deteccao_pct), "sinalizados": int(r.sinalizados),
                      "precisao_pct": float(r.precisao_pct)}
            for r in det.itertuples()
        },
        "deteccao_global_pct": round(100 * det.detectados.sum() / det.injetados.sum(), 2),
        "implausiveis_nao_bloqueados_com_alerta_v10": int(len(
            set(erros.loc[erros.tipo_erro == "valor_implausivel", "relato_id"]) - bloqueados
            & set(achados.loc[achados.regra == "V10", "relato_id"]))),
        "indice_qualidade": {
            "media": round(float(qualidade.indice_qualidade.mean()), 1),
            "minimo": float(qualidade.indice_qualidade.min()),
            "maximo": float(qualidade.indice_qualidade.max()),
            "parceiros_por_faixa": {k: int(v) for k, v in qualidade.faixa.value_counts().sort_index().items()},
        },
    }
    atualizar_metricas("validacao", metricas, c)
    return metricas
