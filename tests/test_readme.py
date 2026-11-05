"""Todo número de resultado dos READMEs precisa existir em reports/metricas.json.

O README.md usa o formato brasileiro (57.510 e 16,47%) e o README.en.md o formato em inglês
(57,510 e 16.47%). Além de conferir os dois contra metricas.json, o teste exige que os dois
arquivos citem exatamente os mesmos números (a seção "English summary" do README.md fica de fora,
porque o README.en.md é a tradução completa).
"""

import json
import re
from collections import Counter

from m5w.config import RAIZ

PADRAO_PT = r"(?<![\w.])(\d{1,3}(?:\.\d{3})+|\d+,\d{1,2})(?=%|\b)"
PADRAO_EN = r"(?<![\w,])(\d{1,3}(?:,\d{3})+|\d+\.\d{1,2})(?=%|\b)"


def _valores(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _valores(v)
    elif isinstance(obj, int | float) and not isinstance(obj, bool):
        yield obj


def _numeros(texto, padrao, milhar, decimal):
    """Lista de (valor, é_decimal) citados no texto."""
    saida = []
    for txt in re.findall(padrao, texto):
        if decimal in txt:
            saida.append((float(txt.replace(decimal, ".")), True))
        else:
            saida.append((int(txt.replace(milhar, "")), False))
    return saida


def _readme_pt():
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    inicio = texto.find("## English summary")
    fim = texto.find("\n## ", inicio + 1)
    return texto if inicio < 0 else texto[:inicio] + texto[fim:]


def _readme_en():
    """README.en.md sem os números que não são resultados e que só o formato em inglês captura:
    numeração de seções (### 2.1, section 4.3) e versões do Python (3.10, 3.12)."""
    texto = (RAIZ / "README.en.md").read_text(encoding="utf-8")
    texto = re.sub(r"^(#+ )\d+(\.\d+)*", r"\1", texto, flags=re.M)
    texto = re.sub(r"\bsection \d+\.\d+", "section", texto)
    return re.sub(r"\b3\.1[02]\b", "", texto)


def _faltando(numeros):
    metricas = list(_valores(json.loads((RAIZ / "reports" / "metricas.json").read_text(encoding="utf-8"))))
    inteiros = {int(v) for v in metricas if float(v).is_integer()}
    decimais = {round(abs(v), 2) for v in metricas} | {round(abs(v), 1) for v in metricas}
    return [v for v, dec in numeros if (v not in decimais if dec else v not in inteiros)]


def test_numeros_do_readme_vem_de_metricas_json():
    faltando = _faltando(_numeros((RAIZ / "README.md").read_text(encoding="utf-8"), PADRAO_PT, ".", ","))
    assert not faltando, f"números do README ausentes de metricas.json: {faltando}"


def test_numeros_do_readme_en_vem_de_metricas_json():
    faltando = _faltando(_numeros(_readme_en(), PADRAO_EN, ",", "."))
    assert not faltando, f"números do README.en.md ausentes de metricas.json: {faltando}"


def test_readme_pt_e_en_citam_os_mesmos_numeros():
    pt = Counter(_numeros(_readme_pt(), PADRAO_PT, ".", ","))
    en = Counter(_numeros(_readme_en(), PADRAO_EN, ",", "."))
    assert pt == en, f"só no README.md: {pt - en}; só no README.en.md: {en - pt}"
