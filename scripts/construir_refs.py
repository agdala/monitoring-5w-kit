"""Constrói as tabelas de referência geográfica versionadas em data/ref/.

Roda uma única vez, fora do pipeline (requer `shapely`, ver requirements-dev.txt).
O pipeline (`make run`) e o CI só leem os arquivos gerados: nenhuma chamada de rede.

Entradas (baixadas manualmente, ver data/ref/FONTES.md):
- municipios.csv de kelvins/municipios-brasileiros (códigos IBGE dos 5.570 municípios);
- geojs-XX-mun.json de tbrugz/geodata-br (malha municipal do IBGE, CC0), um arquivo por UF.

Saídas:
- data/ref/municipios.csv: codigo_ibge, nome, uf, codigo_uf;
- data/ref/uf_malha.geojson: 27 UFs dissolvidas a partir da malha municipal e simplificadas.

Uso:
    python scripts/construir_refs.py --municipios municipios.csv --malha pasta_com_geojs/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

UF_SIGLA = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}
TOLERANCIA_GRAUS = 0.08  # cerca de 9 km: suficiente para um mapa coroplético pequeno


def _arredondar(coords, casas=2):
    if isinstance(coords[0], int | float):
        return [round(coords[0], casas), round(coords[1], casas)]
    return [_arredondar(c, casas) for c in coords]


def construir_municipios(origem: Path, destino: Path) -> None:
    df = pd.read_csv(origem, dtype={"codigo_ibge": int, "codigo_uf": int})
    df["uf"] = df["codigo_uf"].map(UF_SIGLA)
    df = df[["codigo_ibge", "nome", "uf", "codigo_uf"]].sort_values("codigo_ibge")
    assert len(df) >= 5570 and df["uf"].notna().all()
    df.to_csv(destino, index=False)


def construir_malha(pasta: Path, destino: Path) -> None:
    feicoes = []
    for codigo, sigla in sorted(UF_SIGLA.items()):
        dados = json.loads((pasta / f"geojs-{codigo}-mun.json").read_text(encoding="utf-8"))
        geom = unary_union([shape(f["geometry"]).buffer(0) for f in dados["features"]])
        geom = geom.simplify(TOLERANCIA_GRAUS, preserve_topology=True)
        g = mapping(geom)
        feicoes.append({
            "type": "Feature",
            "properties": {"uf": sigla, "codigo_uf": codigo},
            "geometry": {"type": g["type"], "coordinates": _arredondar(json.loads(json.dumps(g["coordinates"])))},
        })
    destino.write_text(json.dumps({"type": "FeatureCollection", "features": feicoes}, separators=(",", ":")),
                       encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--municipios", type=Path, required=True)
    p.add_argument("--malha", type=Path, required=True)
    p.add_argument("--saida", type=Path, default=Path("data/ref"))
    a = p.parse_args()
    a.saida.mkdir(parents=True, exist_ok=True)
    construir_municipios(a.municipios, a.saida / "municipios.csv")
    construir_malha(a.malha, a.saida / "uf_malha.geojson")


if __name__ == "__main__":
    main()
