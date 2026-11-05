import json

import numpy as np
import pandas as pd
import pytest

from m5w.aggregate import comparar_com_gabarito, estimar_pessoas_unicas, totais_por_parceiro
from m5w.disclosure import alocar_proporcional, suprimir
from m5w.tempo import agregar_no_tempo


@pytest.fixture
def serie():
    # dois parceiros, mesmo município, 3 meses
    return pd.DataFrame({
        "parceiro_id": ["A"] * 3 + ["B"] * 3, "municipio_cod": [1] * 6, "indicador": ["X"] * 6,
        "uf": ["RR"] * 6, "mes": ["2025-01", "2025-02", "2025-03"] * 2, "valor": [10, 30, 20, 5, 5, 40],
    })


def test_soma_soma_os_meses(serie):
    assert agregar_no_tempo(serie, "soma", ["uf"])["RR"] == 110


def test_maximo_soma_parceiros_no_mes_e_pega_o_pico(serie):
    # meses: 15, 35, 60 -> pico 60 (e não 30 + 40 = 70, nem a soma 110)
    assert agregar_no_tempo(serie, "maximo", ["uf"])["RR"] == 60


def test_ultimo_pega_o_ultimo_valor_de_cada_serie(serie):
    assert agregar_no_tempo(serie, "ultimo", ["uf"])["RR"] == 20 + 40


def test_regra_desconhecida_falha(serie):
    with pytest.raises(ValueError):
        agregar_no_tempo(serie, "media", ["uf"])


def test_metodos_de_pessoas_unicas_em_exemplo_pequeno():
    tot = pd.DataFrame({"setor": ["abrigo"] * 2, "uf": ["RR"] * 2, "municipio_cod": [1, 1],
                        "parceiro_id": ["A", "B"], "valor": [60, 40]})
    pin = pd.DataFrame({"municipio_cod": [1], "setor": ["abrigo"], "pin": [100]})
    est = estimar_pessoas_unicas(tot, pin).iloc[0]
    assert (est.soma_simples, est.maximo_municipio, est.uniao_independente) == (100, 60, 76)


def test_limites_teoricos_contra_o_gabarito(projeto, quadro, relatos_limpos):
    """Sem erros nos relatos: soma >= gabarito >= máximo, em todo setor x UF; a união fica entre os dois."""
    pin = pd.read_csv(projeto.sintetico / "pin.csv")
    gab = pd.read_csv(projeto.sintetico / "gabarito_pessoas_unicas.csv")
    comp = comparar_com_gabarito(estimar_pessoas_unicas(totais_por_parceiro(relatos_limpos, quadro), pin), gab)
    assert (comp.soma_simples >= comp.gabarito).all()
    assert (comp.maximo_municipio <= comp.gabarito).all()
    assert ((comp.uniao_independente >= comp.maximo_municipio) & (comp.uniao_independente <= comp.soma_simples)).all()


def test_metricas_reportam_os_tres_metodos(projeto):
    m = json.loads((projeto.reports / "metricas.json").read_text())["agregacao"]
    for base in ("erro_metodos_relatos_validos", "erro_metodos_relatos_sem_erros"):
        assert set(m[base]) == {"soma_simples", "maximo_municipio", "uniao_independente"}
    # somar meses de indicadores de estoque ou acumulado sempre infla o total
    assert all(v["inflacao_pct"] > 0 for v in m["soma_indevida_de_estoque"].values())


def test_metas_vs_realizado(projeto):
    mvr = pd.read_csv(projeto.reports / "metas_vs_realizado.csv").dropna(subset=["meta"])
    assert len(mvr) == 115
    np.testing.assert_allclose(mvr.alcance_pct, (100 * mvr.realizado / mvr.meta).round(1))


def test_alocacao_proporcional_preserva_o_total():
    v = alocar_proporcional(101, np.array([3, 3, 3, 1, 0, 0]))
    assert v.sum() == 101 and v[4] == v[5] == 0


def test_supressao_primaria_e_secundaria():
    df = pd.DataFrame({"g": ["a"] * 4, "celula": ["c1", "c2", "c3", "total"], "pessoas": [3, 10, 20, 33]})
    out = suprimir(df, ["g"])
    assert out.suprimido.tolist() == [True, True, False, False]
    assert out.motivo.tolist() == ["primaria", "secundaria", "", ""]


def test_tabela_publicada_nao_tem_celula_de_1_a_4(projeto):
    pub = pd.read_csv(projeto.publicacao / "pessoas_desagregadas_uf.csv")
    assert not pub.pessoas.between(1, 4).any()
    for _, g in pub.groupby(["indicador", "uf"]):
        total_publicado = not g[g.celula == "total"].suprimido.any()
        # com o total publicado, nunca pode haver exatamente uma célula suprimida
        assert not (total_publicado and g[g.celula != "total"].suprimido.sum() == 1)
