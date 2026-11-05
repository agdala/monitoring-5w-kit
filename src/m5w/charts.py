"""Gráficos em SVG gerados pelo próprio código (sem dependência de biblioteca gráfica).

Cores por papel, definidas como variáveis CSS no template (claro e escuro):
- uma série: --series-1 (azul);
- três métodos de pessoas únicas: --series-1..3 em ordem fixa (azul, laranja, verde-água);
- mapa: escala divergente em torno de 100% da meta (vermelho abaixo, cinza na faixa da meta, azul acima).
Toda marca tem <title> (dica ao passar o mouse) e todo gráfico tem uma tabela equivalente no relatório.
"""

from __future__ import annotations

import json
import math
from html import escape
from pathlib import Path

FAIXAS_MAPA = [
    (None, 70, "--div-neg-2", "abaixo de 70%"),
    (70, 90, "--div-neg-1", "70% a 90%"),
    (90, 110, "--div-mid", "90% a 110%"),
    (110, 130, "--div-pos-1", "110% a 130%"),
    (130, None, "--div-pos-2", "130% ou mais"),
]


def _num(v: float, casas: int = 1) -> str:
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def barras_alcance(linhas: list[dict], largura: int = 640) -> str:
    """Barras horizontais de alcance (%) com linha de referência em 100%.

    linhas: [{"rotulo", "grupo", "valor", "dica"}], já na ordem de exibição.
    """
    esq, dir_, alt_barra, gap, topo = 250, 60, 14, 10, 24
    maximo = max(150.0, max(r["valor"] for r in linhas) * 1.05)
    util = largura - esq - dir_
    x = lambda v: esq + util * min(v, maximo) / maximo  # noqa: E731
    partes, y, grupo_atual = [], topo, None
    for r in linhas:
        if r["grupo"] != grupo_atual:
            grupo_atual = r["grupo"]
            y += 6
            partes.append(f'<text x="0" y="{y + 10}" class="t-grupo">{escape(grupo_atual)}</text>')
            y += 18
        w = max(x(r["valor"]) - esq, 2)
        partes.append(
            f'<g class="marca"><title>{escape(r["dica"])}</title>'
            f'<rect x="{esq - 4}" y="{y - gap / 2}" width="{largura - esq}" height="{alt_barra + gap}" class="alvo"/>'
            f'<text x="12" y="{y + alt_barra - 3}" class="t-rotulo">{escape(r["rotulo"])}</text>'
            f'<path d="M{esq},{y} h{w - 4} a4,4 0 0 1 4,4 v{alt_barra - 8} a4,4 0 0 1 -4,4 h{-(w - 4)} z" '
            f'class="barra"/>'
            f'<text x="{x(r["valor"]) + 6}" y="{y + alt_barra - 3}" class="t-valor">{_num(r["valor"])}%</text></g>'
        )
        y += alt_barra + gap
    ref = x(100)
    eixo = (f'<line x1="{ref}" y1="{topo - 6}" x2="{ref}" y2="{y}" class="ref"/>'
            f'<text x="{ref}" y="{topo - 10}" text-anchor="middle" class="t-eixo">meta = 100%</text>')
    return (f'<svg viewBox="0 0 {largura} {y + 6}" role="img" class="grafico" '
            f'aria-label="Alcance das metas por indicador">{eixo}{"".join(partes)}</svg>')


def barras_erro_metodos(grupos: list[str], metodos: dict[str, str], valores: dict, largura: int = 640) -> str:
    """Barras agrupadas e divergentes em torno de 0: erro % de cada método por setor."""
    esq, dir_, alt, gap_grupo, topo = 170, 70, 12, 14, 34
    todos = [abs(valores[g][m]) for g in grupos for m in metodos]
    lim = max(10.0, math.ceil(max(todos) / 10) * 10)
    util = largura - esq - dir_
    zero = esq + util / 2
    x = lambda v: zero + (util / 2) * v / lim  # noqa: E731
    partes, y = [], topo
    for g in grupos:
        partes.append(f'<text x="0" y="{y + 1.5 * alt + 4}" class="t-rotulo">{escape(g)}</text>')
        for i, (m, nome) in enumerate(metodos.items()):
            v = valores[g][m]
            x0, x1 = sorted((zero, x(v)))
            w = max(x1 - x0, 1.5)
            ancora, tx = ("start", x1 + 5) if v >= 0 else ("end", x0 - 5)
            partes.append(
                f'<g class="marca"><title>{escape(g)}: {escape(nome)}, erro de {_num(v)}%</title>'
                f'<rect x="{esq}" y="{y - 1}" width="{util}" height="{alt + 2}" class="alvo"/>'
                f'<rect x="{x0}" y="{y}" width="{w}" height="{alt}" rx="3" style="fill:var(--series-{i + 1})"/>'
                f'<text x="{tx}" y="{y + alt - 2}" text-anchor="{ancora}" class="t-valor">{_num(v)}%</text></g>')
            y += alt + 2
        y += gap_grupo
    eixo = [f'<line x1="{zero}" y1="{topo - 8}" x2="{zero}" y2="{y - gap_grupo + 4}" class="ref"/>']
    for t in (-lim, -lim / 2, lim / 2, lim):
        eixo.append(f'<text x="{x(t)}" y="{topo - 12}" text-anchor="middle" class="t-eixo">'
                    f'{"+" if t > 0 else ""}{_num(t, 0)}%</text>')
    eixo.append(f'<text x="{zero}" y="{topo - 12}" text-anchor="middle" class="t-eixo">0</text>')
    return (f'<svg viewBox="0 0 {largura} {y}" role="img" class="grafico" '
            f'aria-label="Erro percentual de cada método contra o gabarito">{"".join(eixo)}{"".join(partes)}</svg>')


def barra_mini(valor: float, maximo: float = 100, largura: int = 120) -> str:
    w = max(largura * valor / maximo, 2)
    return (f'<svg viewBox="0 0 {largura} 10" width="{largura}" height="10" aria-hidden="true">'
            f'<rect width="{largura}" height="10" rx="3" class="trilho"/>'
            f'<rect width="{w:.1f}" height="10" rx="3" class="barra"/></svg>')


# --------------------------------------------------------------------------------------------
# Mapa
# --------------------------------------------------------------------------------------------
def _projetar(lon: float, lat: float, escala: float) -> tuple[float, float]:
    # equirretangular com correção do cosseno da latitude média do Brasil (~ -14°)
    return ((lon + 74.2) * math.cos(math.radians(14)) * escala, (5.6 - lat) * escala)


def _aneis(geom: dict) -> list[list]:
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [p[0] for p in geom["coordinates"]]


def _centroide(anel: list, escala: float) -> tuple[float, float]:
    pts = [_projetar(lo, la, escala) for lo, la in anel]
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    a *= 0.5
    return (cx / (6 * a), cy / (6 * a)) if a else pts[0]


# rótulo do mapa usa o piso do percentual, para não cruzar a faixa de cor (89,8% vira 89%, não 90%)
AJUSTE_ROTULO = {"RJ": (14, 10), "DF": (0, -2), "SC": (12, 2), "PE": (24, 0), "SP": (-4, 4), "RS": (-4, 0)}


def mapa_alcance(malha: Path, alcance: dict[str, float], largura: int = 560) -> str:
    dados = json.loads(malha.read_text(encoding="utf-8"))
    escala = largura / ((74.2 - 34.0) * math.cos(math.radians(14)))
    altura = (5.6 + 34.0) * escala
    formas, rotulos = [], []
    for f in dados["features"]:
        uf = f["properties"]["uf"]
        aneis = _aneis(f["geometry"])
        d = " ".join(
            "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in (_projetar(lo, la, escala) for lo, la in anel)) + " Z"
            for anel in aneis)
        v = alcance.get(uf)
        if v is None:
            cor, dica = "var(--sem-meta)", f"{uf}: sem meta (sem parceiros no quadro)"
        else:
            var = next(c for lo, hi, c, _ in FAIXAS_MAPA if (lo is None or v >= lo) and (hi is None or v < hi))
            cor, dica = f"var({var})", f"{uf}: {_num(v)}% da meta de pessoas atendidas"
        formas.append(f'<path d="{d}" style="fill:{cor}" class="uf"><title>{escape(dica)}</title></path>')
        if v is not None:
            maior = max(aneis, key=len)
            cx, cy = _centroide(maior, escala)
            dx, dy = AJUSTE_ROTULO.get(uf, (0, 0))
            rotulos.append(f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="middle" class="t-mapa">'
                           f'<tspan x="{cx + dx:.1f}">{uf}</tspan>'
                           f'<tspan x="{cx + dx:.1f}" dy="11">{math.floor(v)}%</tspan></text>')
    legenda, lx = [], 10
    for _, _, var, nome in FAIXAS_MAPA:
        legenda.append(f'<rect x="{lx}" y="{altura + 12}" width="14" height="14" rx="3" style="fill:var({var})" '
                       f'class="uf"/><text x="{lx + 19}" y="{altura + 24}" class="t-eixo">{nome}</text>')
        lx += 19 + 7 * len(nome) + 14
    legenda.append(f'<rect x="{lx}" y="{altura + 12}" width="14" height="14" rx="3" style="fill:var(--sem-meta)" '
                   f'class="uf"/><text x="{lx + 19}" y="{altura + 24}" class="t-eixo">sem meta</text>')
    return (f'<svg viewBox="0 0 {largura + 140} {altura + 34:.0f}" role="img" class="grafico mapa" '
            f'aria-label="Mapa do Brasil por UF com o percentual de alcance da meta de pessoas atendidas">'
            f'{"".join(formas)}{"".join(rotulos)}{"".join(legenda)}</svg>')
