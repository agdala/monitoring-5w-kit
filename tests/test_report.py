import re


def test_relatorio_tem_as_secoes_e_nenhum_recurso_externo(projeto):
    html = (projeto.reports / "relatorio.html").read_text(encoding="utf-8")
    for secao in ("resumo", "metas", "mapa", "dupla-contagem", "qualidade"):
        assert f'id="{secao}"' in html
    assert "Dados 100% sintéticos" in html
    assert html.count('class="uf"') >= 27  # 27 UFs no mapa (+ legenda)
    # arquivo autocontido: nenhum script, folha de estilo ou imagem externa
    assert not re.search(r'<(script|link|img)[^>]+(src|href)="https?://', html)


def test_relatorio_e_deterministico(projeto):
    from m5w import report
    antes = (projeto.reports / "relatorio.html").read_text(encoding="utf-8")
    report.executar(projeto)
    assert antes == (projeto.reports / "relatorio.html").read_text(encoding="utf-8")
