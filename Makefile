.PHONY: run test lint limpar

run:      ## pipeline completo: gerar, validar, agregar e publicar o relatório
	python -m m5w run

test:     ## testes (pytest)
	pytest -q

lint:     ## estilo e erros comuns (ruff)
	ruff check .

limpar:   ## apaga os dados sintéticos gerados (reports/ é versionado)
	rm -rf data/sintetico
