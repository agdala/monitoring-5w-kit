"""Etapa de relatório: reports/relatorio.html, um arquivo único (SVG embutido, sem rede)."""

from __future__ import annotations

import json

import pandas as pd
from jinja2 import Environment, PackageLoader, select_autoescape

from . import charts
from .aggregate import METODOS
from .config import Caminhos, carregar_quadro
from .rules import REGRAS

BASE_URL_REPO = "https://github.com/agdala/monitoring-5w-kit"


def _num(v, casas: int = 0) -> str:
    return charts._num(float(v), casas)


def montar_contexto(c: Caminhos) -> dict:
    q = carregar_quadro(c)
    m = json.loads((c.reports / "metricas.json").read_text(encoding="utf-8"))
    ger, val, agr = m["geracao"], m["validacao"], m["agregacao"]
    por_ind = pd.read_csv(c.reports / "alcance_por_indicador.csv")
    por_uf = pd.read_csv(c.reports / "alcance_pessoas_por_uf.csv")
    mvr = pd.read_csv(c.reports / "metas_vs_realizado.csv")
    comp = pd.read_csv(c.reports / "pessoas_unicas_metodos.csv")
    det = pd.read_csv(c.reports / "deteccao_erros.csv")
    qual = pd.read_csv(c.reports / "qualidade_parceiros.csv")
    pend = pd.read_csv(c.reports / "pendencias_por_parceiro.csv")

    ordem_setor = list(q.setores)
    por_ind["ordem"] = por_ind.setor.map(ordem_setor.index)
    por_ind = por_ind.sort_values(["ordem", "indicador"])
    linhas_alc = [{
        "rotulo": f"{r.indicador} {r.indicador_nome[:30]}{'…' if len(r.indicador_nome) > 30 else ''}",
        "grupo": r.setor_nome, "valor": r.alcance_pct,
        "dica": f"{r.indicador} {r.indicador_nome}: {_num(r.realizado)} de {_num(r.meta)} ({_num(r.alcance_pct, 1)}%)",
    } for r in por_ind.itertuples()]

    erros_val = agr["erro_metodos_relatos_validos"]
    grupos = [q.setores[s] for s in ordem_setor] + ["Total"]
    valores = {q.setores[s]: {mt: erros_val[mt]["erro_por_setor_pct"][s] for mt in METODOS} for s in ordem_setor}
    valores["Total"] = {mt: erros_val[mt]["erro_total_pct"] for mt in METODOS}

    oficial = q.metodo_oficial
    estimado = agr["pessoas_unicas_estimadas"][oficial]
    gabarito = agr["pessoas_unicas_gabarito"]
    metodos_tab = [{
        "nome": nome, "chave": mt, "oficial": mt == oficial, "estimado": agr["pessoas_unicas_estimadas"][mt],
        "erro_validos": erros_val[mt]["erro_total_pct"],
        "erro_sem_erros": agr["erro_metodos_relatos_sem_erros"][mt]["erro_total_pct"],
        "mape": erros_val[mt]["erro_absoluto_medio_setor_uf_pct"],
    } for mt, nome in METODOS.items()]

    pend_resumo = (pend.groupby(["parceiro_id", "severidade"]).size().unstack(fill_value=0)
                   .reindex(columns=["erro", "alerta"], fill_value=0))
    qual = qual.join(pend_resumo, on="parceiro_id").fillna({"erro": 0, "alerta": 0})
    qual["barra"] = [charts.barra_mini(v) for v in qual.indice_qualidade]

    melhor = min(metodos_tab, key=lambda r: abs(r["erro_sem_erros"]))
    abaixo = mvr[mvr.alcance_pct < 70].sort_values("alcance_pct")
    achados = [
        f"{_num(val['relatos_bloqueados'])} de {_num(val['relatos_recebidos'])} relatos "
        f"({_num(val['pct_relatos_bloqueados'], 1)}%) foram bloqueados por erro e voltam ao parceiro com "
        f"mensagem de correção; {_num(val['relatos_com_alerta'])} seguem na consolidação com alerta.",
        f"As regras detectaram {_num(val['deteccao_global_pct'], 1)}% dos erros injetados. A mais fraca é a "
        f"V07 (valor implausível): {_num(val['deteccao_por_regra']['V07']['taxa_deteccao_pct'], 1)}%, porque "
        f"um zero a mais em série pequena se confunde com variação real.",
        f"Somar os parceiros superestima as pessoas únicas em "
        f"{_num(agr['erro_metodos_relatos_sem_erros']['soma_simples']['erro_total_pct'], 1)}% (relatos sem erros); "
        f"o máximo por município subestima em "
        f"{_num(abs(agr['erro_metodos_relatos_sem_erros']['maximo_municipio']['erro_total_pct']), 1)}%. "
        f"O método de menor erro foi: {melhor['nome'].lower()}.",
        f"{agr['metas_atingidas']} de {agr['metas_indicador_uf']} metas (indicador x UF) foram atingidas; "
        f"{len(abaixo)} estão abaixo de 70%.",
    ]
    return {
        "q": q, "ger": ger, "val": val, "agr": agr, "num": _num, "achados": achados,
        "kpis": [
            ("Relatos recebidos", _num(val["relatos_recebidos"]), f"{ger['parceiros']} parceiros, 12 meses"),
            ("Bloqueados por erro", f"{_num(val['pct_relatos_bloqueados'], 1)}%",
             f"{_num(val['relatos_bloqueados'])} relatos"),
            ("Erros injetados detectados", f"{_num(val['deteccao_global_pct'], 1)}%",
             f"{_num(sum(r['injetados'] for r in val['deteccao_por_regra'].values()))} erros"),
            ("Pessoas únicas estimadas", _num(estimado),
             f"gabarito: {_num(gabarito)} ({'+' if estimado >= gabarito else ''}"
             f"{_num(100 * (estimado - gabarito) / gabarito, 1)}%)"),
            ("Metas atingidas", f"{agr['metas_atingidas']} de {agr['metas_indicador_uf']}", "indicador x UF"),
        ],
        "svg_alcance": charts.barras_alcance(linhas_alc),
        "por_ind": por_ind.to_dict("records"),
        "svg_mapa": charts.mapa_alcance(c.ref / "uf_malha.geojson", dict(zip(por_uf.uf, por_uf.alcance_pct))),
        "por_uf": por_uf.sort_values("alcance_pct").to_dict("records"),
        "svg_metodos": charts.barras_erro_metodos(grupos, METODOS, valores),
        "metodos": metodos_tab, "nome_oficial": METODOS[oficial],
        "comp": comp.sort_values(["setor", "uf"]).assign(setor=lambda d: d.setor.map(q.setores)).to_dict("records"),
        "regras": REGRAS, "det": det.to_dict("records"),
        "qual": qual.to_dict("records"),
        "abaixo": abaixo.to_dict("records"),
        "repo": BASE_URL_REPO,
    }


def executar(caminhos: Caminhos | None = None) -> dict:
    c = caminhos or Caminhos()
    env = Environment(loader=PackageLoader("m5w", "templates"), autoescape=select_autoescape(["html", "j2"]))
    html = env.get_template("relatorio.html.j2").render(**montar_contexto(c))
    arq = c.reports / "relatorio.html"
    arq.write_text(html, encoding="utf-8")
    return {"relatorio": str(arq.relative_to(c.raiz)), "bytes": len(html.encode("utf-8"))}
