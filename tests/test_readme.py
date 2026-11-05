"""Todo número de resultado do README precisa existir em reports/metricas.json."""

import json
import re

from m5w.config import RAIZ


def _valores(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _valores(v)
    elif isinstance(obj, int | float) and not isinstance(obj, bool):
        yield obj


def test_numeros_do_readme_vem_de_metricas_json():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    metricas = list(_valores(json.loads((RAIZ / "reports" / "metricas.json").read_text(encoding="utf-8"))))
    inteiros = {int(v) for v in metricas if float(v).is_integer()}
    decimais = {round(abs(v), 2) for v in metricas} | {round(abs(v), 1) for v in metricas}
    faltando = []
    for txt in re.findall(r"(?<![\w.])(\d{1,3}(?:\.\d{3})+|\d+,\d{1,2})(?=%|\b)", readme):
        if "," in txt:
            ok = float(txt.replace(",", ".")) in decimais
        else:
            ok = int(txt.replace(".", "")) in inteiros
        if not ok:
            faltando.append(txt)
    assert not faltando, f"números do README ausentes de metricas.json: {faltando}"
