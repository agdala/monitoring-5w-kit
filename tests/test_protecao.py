"""Nenhum dado de pessoa é gravado; nenhum segredo versionado."""

import re
import subprocess

from m5w.config import RAIZ


def test_populacao_sintetica_nao_e_gravada(projeto):
    arquivos = {p.name for p in projeto.sintetico.iterdir()}
    assert not any("pessoas.csv" == a or "vinculos" in a for a in arquivos)


def test_nenhum_segredo_versionado():
    versionados = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True).stdout.split()
    assert not [f for f in versionados if re.search(r"(\.env|\.pem|\.key|credentials|secret)", f, re.I)]
