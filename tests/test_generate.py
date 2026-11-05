import pandas as pd

from m5w import generate
from m5w.config import CELULAS, carregar_municipios


def test_semente_fixa_reproduz_os_relatos(projeto, relatos):
    generate.executar(projeto)
    pd.testing.assert_frame_equal(relatos, pd.read_csv(projeto.sintetico / "relatos.csv"))


def test_quadro_tem_4_setores_e_2_a_3_indicadores_por_setor(quadro):
    contagem = quadro.indicadores.groupby("setor").size()
    assert len(contagem) == 4 and contagem.between(2, 3).all()
    assert set(quadro.indicadores.agregacao_tempo) == {"soma", "maximo", "ultimo"}
    assert set(quadro.metas().indicador) == set(quadro.indicadores.index)


def test_relatos_limpos_sao_consistentes(projeto, relatos_limpos, quadro):
    ref = carregar_municipios(projeto).set_index("codigo_ibge")
    assert relatos_limpos.municipio_cod.isin(ref.index).all()
    assert (relatos_limpos.municipio_cod.map(ref.uf) == relatos_limpos.uf).all()
    desag = relatos_limpos.indicador.map(quadro.indicadores.desagregado)
    d = relatos_limpos[desag]
    assert (d[CELULAS].sum(axis=1) == d.valor).all()
    assert not relatos_limpos.duplicated(["parceiro_id", "mes", "indicador", "municipio_cod"]).any()


def test_sobreposicao_real_entre_parceiros(projeto, relatos_limpos, quadro):
    """A soma dos relatos de pessoas novas supera o gabarito de pessoas únicas: há dupla contagem."""
    gab = pd.read_csv(projeto.sintetico / "gabarito_pessoas_unicas.csv").pessoas_unicas.sum()
    principais = quadro.indicadores[quadro.indicadores.principal].index
    soma = relatos_limpos[relatos_limpos.indicador.isin(principais)].valor.sum()
    assert 1.05 * gab < soma < 1.5 * gab


def test_atuacao_concentrada_e_espalhada(relatos_limpos):
    por_uf = relatos_limpos.groupby("uf").parceiro_id.nunique()
    assert por_uf.max() >= 5 and (por_uf <= 2).sum() >= 4


def test_erros_injetados_em_proporcao_realista(relatos, erros):
    assert erros.relato_id.is_unique and erros.relato_id.isin(relatos.relato_id).all()
    assert 0.08 < len(erros) / len(relatos) < 0.25
    assert erros.tipo_erro.nunique() == 8
