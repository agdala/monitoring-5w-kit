"""Linha de comando: m5w generate | validate | aggregate | report | run."""

from __future__ import annotations

import argparse
import json
import sys

from .config import Caminhos


def _generate(c: Caminhos) -> dict:
    from . import generate
    return generate.executar(c)


def _validate(c: Caminhos) -> dict:
    from . import validate
    return validate.executar(c)


def _aggregate(c: Caminhos) -> dict:
    from . import aggregate
    return aggregate.executar(c)


def _report(c: Caminhos) -> dict:
    from . import report
    return report.executar(c)


ETAPAS = {"generate": _generate, "validate": _validate, "aggregate": _aggregate, "report": _report}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="m5w", description="Monitoramento 5W com dados sintéticos.")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("generate", help="gera parceiros, população sintética, relatos e erros injetados")
    sub.add_parser("validate", help="aplica as regras de validação aos relatos")
    sub.add_parser("aggregate", help="agrega no tempo, estima pessoas únicas e compara com as metas")
    sub.add_parser("report", help="gera reports/relatorio.html")
    sub.add_parser("run", help="executa todas as etapas em sequência")
    a = p.parse_args(argv)
    c = Caminhos()
    etapas = list(ETAPAS) if a.comando == "run" else [a.comando]
    for etapa in etapas:
        if etapa not in ETAPAS:
            print(f"etapa '{etapa}' ainda não implementada", file=sys.stderr)
            return 2
        resultado = ETAPAS[etapa](c)
        print(f"[{etapa}] " + json.dumps(resultado, ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
