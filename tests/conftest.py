"""Fixture de sessão: roda o pipeline numa cópia temporária do projeto (config + data/ref)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

from m5w.config import RAIZ, Caminhos, carregar_quadro


@pytest.fixture(scope="session")
def projeto(tmp_path_factory) -> Caminhos:
    raiz = Path(tmp_path_factory.mktemp("projeto"))
    shutil.copytree(RAIZ / "config", raiz / "config")
    shutil.copytree(RAIZ / "data" / "ref", raiz / "data" / "ref")
    c = Caminhos(raiz=raiz)
    from m5w import cli
    for etapa in cli.ETAPAS.values():
        etapa(c)
    return c


@pytest.fixture(scope="session")
def quadro(projeto):
    return carregar_quadro(projeto)


@pytest.fixture(scope="session")
def relatos(projeto) -> pd.DataFrame:
    return pd.read_csv(projeto.sintetico / "relatos.csv")


@pytest.fixture(scope="session")
def relatos_limpos(projeto) -> pd.DataFrame:
    return pd.read_csv(projeto.sintetico / "relatos_sem_erros.csv")


@pytest.fixture(scope="session")
def erros(projeto) -> pd.DataFrame:
    return pd.read_csv(projeto.sintetico / "erros_injetados.csv")
