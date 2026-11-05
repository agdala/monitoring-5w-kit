"""Testes por regra: relatos limpos não geram erro; cada mutação dispara a sua regra."""

import numpy as np
import pandas as pd
import pytest

from m5w.config import carregar_gerador, carregar_municipios
from m5w.rules import REGRAS, REGRAS_POR_CODIGO, aplicar_regras, preparar


@pytest.fixture(scope="module")
def base(projeto, relatos_limpos):
    rel = relatos_limpos.copy()
    rel.insert(0, "relato_id", [f"L{i:05d}" for i in range(len(rel))])
    return rel


@pytest.fixture(scope="module")
def validar(projeto, quadro):
    muns = carregar_municipios(projeto)
    pin = pd.read_csv(projeto.sintetico / "pin.csv")
    prazo = carregar_gerador(projeto)["prazo_dia"]
    return lambda rel: aplicar_regras(preparar(rel, quadro, muns, pin, prazo))


def test_regras_declaradas_uma_vez_com_codigo_unico():
    codigos = [r.codigo for r in REGRAS]
    assert codigos == sorted(set(codigos)) and len(codigos) == 10
    assert {r.severidade for r in REGRAS} == {"erro", "alerta"}
    assert all(r.mensagem for r in REGRAS)


def test_relatos_limpos_nao_tem_erro_deterministico(base, validar):
    achados = validar(base)
    deterministicas = {"V01", "V02", "V03", "V04", "V05", "V06", "V09"}
    assert achados[achados.regra.isin(deterministicas)].empty
    # heurísticas podem ter falso positivo, mas raro (<1% dos relatos limpos)
    assert len(achados[achados.severidade == "erro"]) < 0.01 * len(base)


def _alvo(base, quadro, desagregado=True):
    ind = base.indicador.map(quadro.indicadores.desagregado)
    return base[(ind == desagregado) & (base.valor >= 5)].index[0]


MUTACOES = {
    "V01": lambda r, i, q: r.assign(mes=r.mes.where(r.index != i, "2024-13")),
    "V02": lambda r, i, q: r.assign(indicador=r.indicador.where(r.index != i, "PRO01")),
    "V03": lambda r, i, q: r.assign(municipio_cod=r.municipio_cod.where(r.index != i, 140010)),
    "V04": lambda r, i, q: r.assign(municipio_cod=r.municipio_cod.where(
        r.index != i, 3550308 if r.at[i, "uf"] != "SP" else 1400100)),
    "V05": lambda r, i, q: pd.concat([r, r.loc[[i]].assign(relato_id="L99999")], ignore_index=True),
    "V06": lambda r, i, q: r.assign(f_18_59=r.f_18_59.where(r.index != i, r.f_18_59 + 2)),
    "V07": lambda r, i, q: r.assign(valor=r.valor.where(r.index != i, -1)),
    "V09": lambda r, i, q: r.assign(data_envio=r.data_envio.where(r.index != i, "2026-06-30")),
}


@pytest.mark.parametrize("codigo", sorted(MUTACOES))
def test_cada_regra_dispara_na_sua_mutacao(codigo, base, validar, quadro):
    i = _alvo(base, quadro)
    rel = MUTACOES[codigo](base, i, quadro)
    achados = validar(rel)
    alvo_id = "L99999" if codigo == "V05" else rel.at[i, "relato_id"]
    assert alvo_id in set(achados.loc[achados.regra == codigo, "relato_id"])
    assert REGRAS_POR_CODIGO[codigo].mensagem  # mensagem formatada sem KeyError
    assert achados.loc[achados.relato_id == alvo_id, "mensagem"].str.len().gt(20).all()


def test_v08_detecta_serie_acumulada_desde_o_meio_do_ano(base, validar, quadro):
    soma = base.indicador.map(quadro.indicadores.agregacao_tempo) == "soma"
    chave = ["parceiro_id", "municipio_cod", "indicador"]
    serie = base[soma & ~base.indicador.map(quadro.indicadores.desagregado)].groupby(chave).filter(
        lambda g: len(g) == 12 and (g.valor > 0).all())
    primeira = serie.groupby(chave).ngroup() == 0
    idx = serie[primeira].sort_values("mes").index
    rel = base.copy()
    v = rel.loc[idx, "valor"].to_numpy()
    rel.loc[idx[5:], "valor"] = np.cumsum(v)[5:]
    achados = validar(rel)
    marcados = set(achados.loc[achados.regra == "V08", "relato_id"])
    assert set(rel.loc[idx[5:], "relato_id"]) <= marcados
    assert not set(rel.loc[idx[:5], "relato_id"]) & marcados


def test_v10_e_alerta_e_nao_bloqueia(projeto):
    validos = pd.read_csv(projeto.reports / "relatos_validos.csv")
    assert validos.alertas.fillna("").str.contains("V10").any()


# Taxa de detecção contra o que foi injetado: regras determinísticas detectam tudo; as
# heurísticas têm piso explícito, para que uma piora apareça no CI.
PISOS = {"V02": 100, "V03": 100, "V04": 100, "V05": 100, "V06": 100, "V09": 100, "V08": 90, "V07": 50}


@pytest.mark.parametrize("codigo", sorted(PISOS))
def test_taxa_de_deteccao_por_tipo_de_erro(codigo, projeto):
    det = pd.read_csv(projeto.reports / "deteccao_erros.csv").set_index("regra")
    assert det.at[codigo, "injetados"] > 0
    assert det.at[codigo, "taxa_deteccao_pct"] >= PISOS[codigo]
    assert det.at[codigo, "precisao_pct"] >= 80


def test_pendencias_e_indice_de_qualidade(projeto):
    pend = pd.read_csv(projeto.reports / "pendencias_por_parceiro.csv")
    q = pd.read_csv(projeto.reports / "qualidade_parceiros.csv")
    assert set(pend.severidade) == {"erro", "alerta"}
    assert q.indice_qualidade.between(0, 100).all() and len(q) == 25
    assert set(q.faixa) <= {"A", "B", "C"}
