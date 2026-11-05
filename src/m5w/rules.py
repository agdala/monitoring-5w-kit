"""Regras de validação dos relatos, declaradas uma única vez.

Cada regra tem código, severidade (erro bloqueia o relato na consolidação, alerta não bloqueia),
mensagem acionável para o parceiro e a função que marca os relatos que a violam.
`tipo_injetado` liga a regra ao erro que o gerador injeta, para medir a taxa de detecção.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import CELULAS

OBRIGATORIOS = ["parceiro_id", "mes", "uf", "municipio_cod", "setor", "indicador", "valor", "data_envio"]
CHAVE_RELATO = ["parceiro_id", "mes", "indicador", "municipio_cod"]
SERIE = ["parceiro_id", "municipio_cod", "indicador"]
FATOR_IMPLAUSIVEL = 10
FATOR_ATIPICO = 4
PISO_MEDIANA_IMPLAUSIVEL = 1  # era 3: deixava passar "zero a mais" em séries de 1 a 4 (ex.: SAU-03)
PISO_MEDIANA_ATIPICO = 3


@dataclass(frozen=True)
class Regra:
    codigo: str
    nome: str
    severidade: str  # "erro" | "alerta"
    mensagem: str  # formatada com as colunas do relato enriquecido
    verificar: Callable[[pd.DataFrame], pd.Series]
    tipo_injetado: str | None = None


# --------------------------------------------------------------------------------------------
# Funções de verificação. Recebem o relato enriquecido por `preparar` e devolvem uma máscara.
# --------------------------------------------------------------------------------------------
def _campos(d: pd.DataFrame) -> pd.Series:
    faltando = d[OBRIGATORIOS].isna().any(axis=1)
    return faltando | ~d.mes.astype(str).str.fullmatch(rf"{d.attrs['ano']}-(0[1-9]|1[0-2])") | d.prazo.isna()


def _indicador(d):
    return d.indicador.notna() & ~d.no_quadro


def _municipio_invalido(d):
    return d.municipio_cod.notna() & d.uf_correta.isna()


def _fora_uf(d):
    return d.uf_correta.notna() & (d.uf_correta != d.uf)


def _duplicado(d):
    ordem = d.sort_values(["data_envio", "relato_id"], kind="mergesort")
    dup = ordem.duplicated(CHAVE_RELATO, keep="first")
    return dup.reindex(d.index)


def _desagregacao(d):
    return d.desagregado & (d[CELULAS].isna().any(axis=1) | (d.soma_celulas != d.valor))


def _implausivel(d):
    acima_pin = d.pessoas & d.pin.notna() & (d.valor > d.pin)
    limiar = FATOR_IMPLAUSIVEL * d.mediana_serie.clip(lower=PISO_MEDIANA_IMPLAUSIVEL)
    acima_serie = d.n_serie.ge(3) & (d.valor >= limiar)
    return (d.valor < 0) | acima_pin | acima_serie


def _cresce(v: np.ndarray, min_altas: int) -> bool:
    dif = np.diff(v)
    return bool((dif >= 0).all() and (dif > 0).sum() >= min_altas)


def _inicio_acumulado(v: np.ndarray) -> int | None:
    """Posição a partir da qual a série parece acumulada, ou None.

    Caso 1: a série inteira (6 meses ou mais) só cresce e termina em 3 vezes o primeiro valor.
    Caso 2: a partir de um mês k (com 3 meses antes e 4 depois), a série só cresce e todo valor
    fica 2,5 vezes acima da mediana dos meses anteriores: o parceiro passou a mandar o acumulado.
    """
    if len(v) >= 6 and _cresce(v, 4) and v[-1] >= 3 * max(v[0], 1):
        return 0
    for k in range(3, len(v) - 3):
        if _cresce(v[k:], 3) and v[k:].min() >= 2.5 * max(np.median(v[:k]), 1):
            return k
    return None


def _acumulado(d):
    """Indicador mensal (soma) relatado como acumulado no ano."""
    alvo = d[d.regra_tempo.eq("soma")].drop_duplicates(CHAVE_RELATO).sort_values("mes")
    marcados: list[int] = []
    for _, g in alvo.groupby(SERIE):
        k = _inicio_acumulado(g.valor.to_numpy())
        if k is not None:
            marcados.extend(g.relato_id.iloc[k:])
    return d.relato_id.isin(marcados)


def _fora_prazo(d):
    return d.data_envio.notna() & d.prazo.notna() & (d.data_envio > d.prazo)


def _atipico(d):
    alvo = d.regra_tempo.isin(["soma", "maximo"]) & d.n_serie.ge(3)
    limiar = FATOR_ATIPICO * d.mediana_serie.clip(lower=PISO_MEDIANA_ATIPICO)
    return alvo & (d.valor > limiar) & ~_implausivel(d)


REGRAS: list[Regra] = [
    Regra("V01", "Campos obrigatórios e período", "erro",
          "Faltam campos obrigatórios ou o mês está fora de {ano}. Preencha parceiro, mês (AAAA-MM), UF, "
          "município, setor, indicador, valor e data de envio.", _campos),
    Regra("V02", "Indicador fora do quadro", "erro",
          "O indicador '{indicador}' não existe no quadro vigente. Use o código exato do quadro "
          "(ex.: PRO-01, com hífen e dois dígitos) e reenvie o relato.", _indicador, "indicador_fora_do_quadro"),
    Regra("V03", "Código de município inválido", "erro",
          "O código de município {municipio_cod} não existe na tabela do IBGE. Use o código de 7 dígitos "
          "(o de 6 dígitos não tem o dígito verificador).", _municipio_invalido, "municipio_invalido"),
    Regra("V04", "Município fora da UF", "erro",
          "O município {municipio_cod} ({municipio_nome}) pertence a {uf_correta}, não à UF {uf} informada. "
          "Corrija a UF ou o código do município.", _fora_uf, "municipio_fora_uf"),
    Regra("V05", "Relato duplicado", "erro",
          "Já existe relato de {indicador} para o município {municipio_cod} em {mes}. Mantivemos o primeiro "
          "envio. Se o valor mudou, peça a correção do relato original em vez de enviar outro.",
          _duplicado, "relato_duplicado"),
    Regra("V06", "Desagregação não soma o total", "erro",
          "As células de sexo e faixa etária somam {soma_celulas} e o total informado é {valor}. Preencha as "
          "6 células (use 0 quando não houver pessoas) de forma que a soma seja igual ao total.",
          _desagregacao, "desagregacao_inconsistente"),
    Regra("V07", "Valor implausível", "erro",
          "O valor {valor} de {indicador} em {municipio_cod} é implausível: supera a população em necessidade "
          "do município ou chega a 10 vezes a mediana do parceiro. Confira se há zeros a mais.",
          _implausivel, "valor_implausivel"),
    Regra("V08", "Acumulado informado como mensal", "erro",
          "A partir de {mes}, a série de {indicador} em {municipio_cod} cresce todos os meses, como um total "
          "acumulado. Este indicador é mensal: informe só o que aconteceu em cada mês e reenvie esses meses.",
          _acumulado, "acumulado_como_mensal"),
    Regra("V09", "Relato fora do prazo", "alerta",
          "Relato de {mes} enviado em {data_envio:%d/%m/%Y}, depois do prazo de {prazo:%d/%m/%Y}. O dado entra "
          "na consolidação, mas atrasa o boletim: envie até o dia {prazo_dia} do mês seguinte.",
          _fora_prazo, "fora_do_prazo"),
    Regra("V10", "Variação atípica", "alerta",
          "O valor {valor} de {indicador} em {municipio_cod} está mais de 4 vezes acima da mediana do parceiro "
          "para este indicador e município. Confirme o valor ou registre a explicação.", _atipico),
]
REGRAS_POR_CODIGO = {r.codigo: r for r in REGRAS}


def preparar(rel: pd.DataFrame, quadro, municipios: pd.DataFrame, pin: pd.DataFrame, prazo_dia: int) -> pd.DataFrame:
    """Enriquece os relatos com as referências que as regras usam (quadro, IBGE, PIN, prazo, séries)."""
    d = rel.copy()
    d.attrs["ano"] = quadro.ano
    ind = quadro.indicadores
    d["no_quadro"] = d.indicador.isin(ind.index)
    d["regra_tempo"] = d.indicador.map(ind.agregacao_tempo)
    d["desagregado"] = d.indicador.map(ind.desagregado.to_dict()).eq(True)
    d["pessoas"] = d.indicador.map(ind.unidade).eq("pessoas")
    ref = municipios.set_index("codigo_ibge")
    d["uf_correta"] = d.municipio_cod.map(ref.uf)
    d["municipio_nome"] = d.municipio_cod.map(ref.nome)
    d = d.merge(pin[["municipio_cod", "setor", "pin"]], on=["municipio_cod", "setor"], how="left")
    d.attrs["ano"] = quadro.ano
    d["soma_celulas"] = d[CELULAS].sum(axis=1, min_count=1).fillna(0).astype(int)
    d["data_envio"] = pd.to_datetime(d.data_envio, errors="coerce")
    inicio_mes = pd.to_datetime(d.mes.astype(str) + "-01", format="%Y-%m-%d", errors="coerce")
    d["prazo"] = inicio_mes + pd.offsets.MonthBegin(1) + pd.Timedelta(days=prazo_dia - 1)
    d["prazo_dia"] = prazo_dia
    d["ano"] = quadro.ano
    g = d.groupby(SERIE).valor
    d["mediana_serie"] = g.transform("median")
    d["n_serie"] = g.transform("size")
    return d


def aplicar_regras(d: pd.DataFrame) -> pd.DataFrame:
    """Devolve uma linha por (relato, regra violada), com severidade e mensagem para o parceiro."""
    achados = []
    for r in REGRAS:
        mask = r.verificar(d).fillna(False).astype(bool)
        for _, linha in d[mask].iterrows():
            achados.append({
                "relato_id": linha.relato_id, "regra": r.codigo, "regra_nome": r.nome,
                "severidade": r.severidade, "mensagem": r.mensagem.format_map(linha.to_dict()),
            })
    return pd.DataFrame(achados, columns=["relato_id", "regra", "regra_nome", "severidade", "mensagem"])
