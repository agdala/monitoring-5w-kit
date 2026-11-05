"""Caminhos do projeto e leitura do quadro de indicadores."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
SEXOS = ["f", "m"]
FAIXAS = ["0_17", "18_59", "60m"]
CELULAS = [f"{s}_{f}" for s in SEXOS for f in FAIXAS]


@dataclass
class Caminhos:
    raiz: Path = RAIZ

    @property
    def config(self) -> Path:
        return self.raiz / "config"

    @property
    def ref(self) -> Path:
        return self.raiz / "data" / "ref"

    @property
    def sintetico(self) -> Path:
        return self.raiz / "data" / "sintetico"

    @property
    def reports(self) -> Path:
        return self.raiz / "reports"

    @property
    def publicacao(self) -> Path:
        return self.reports / "publicacao"

    def garantir(self) -> None:
        for p in (self.sintetico, self.reports, self.publicacao):
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class Quadro:
    """Quadro de indicadores: setores, indicadores, regras de agregação e metas."""

    bruto: dict
    indicadores: pd.DataFrame = field(init=False)

    def __post_init__(self) -> None:
        linhas = []
        for setor, s in self.bruto["setores"].items():
            for cod, ind in s["indicadores"].items():
                linhas.append({
                    "indicador": cod,
                    "setor": setor,
                    "setor_nome": s["nome"],
                    "indicador_nome": ind["nome"],
                    "unidade": ind["unidade"],
                    "agregacao_tempo": ind["agregacao_tempo"],
                    "desagregado": bool(ind.get("desagregacoes")),
                    "principal": bool(ind.get("principal", False)),
                })
        self.indicadores = pd.DataFrame(linhas).set_index("indicador")

    @property
    def ano(self) -> int:
        return int(self.bruto["ano"])

    @property
    def limiar(self) -> int:
        return int(self.bruto.get("limiar_divulgacao", 5))

    @property
    def metodo_oficial(self) -> str:
        return self.bruto["metodo_oficial_pessoas_unicas"]

    @property
    def setores(self) -> dict[str, str]:
        return {k: v["nome"] for k, v in self.bruto["setores"].items()}

    def principal(self, setor: str) -> str:
        df = self.indicadores
        return df[(df.setor == setor) & df.principal].index[0]

    def metas(self) -> pd.DataFrame:
        linhas = [
            {"indicador": ind, "uf": uf, "meta": int(v)}
            for ind, por_uf in (self.bruto.get("metas") or {}).items()
            for uf, v in por_uf.items()
        ]
        return pd.DataFrame(linhas, columns=["indicador", "uf", "meta"])


def carregar_quadro(caminhos: Caminhos | None = None) -> Quadro:
    c = caminhos or Caminhos()
    return Quadro(yaml.safe_load((c.config / "quadro.yaml").read_text(encoding="utf-8")))


def carregar_gerador(caminhos: Caminhos | None = None) -> dict:
    c = caminhos or Caminhos()
    return yaml.safe_load((c.config / "gerador.yaml").read_text(encoding="utf-8"))


def carregar_municipios(caminhos: Caminhos | None = None) -> pd.DataFrame:
    c = caminhos or Caminhos()
    return pd.read_csv(c.ref / "municipios.csv", dtype={"codigo_ibge": "int64"})


def atualizar_metricas(secao: str, valores: dict, caminhos: Caminhos | None = None) -> None:
    """Grava uma seção de reports/metricas.json, preservando as demais (saída determinística)."""
    c = caminhos or Caminhos()
    arq = c.reports / "metricas.json"
    dados = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    dados[secao] = valores
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
