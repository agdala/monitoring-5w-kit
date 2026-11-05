"""Gerador de dados sintéticos.

Ordem de geração (o que torna o gabarito confiável):
1. parceiros fictícios e onde atuam (setor x município);
2. população em necessidade (PIN) por município e setor, como numa avaliação de necessidades;
3. população sintética de pessoas únicas atendidas, cada uma ligada a um ou mais parceiros
   (encaminhamento entre parceiros do mesmo município gera a sobreposição);
4. relatos mensais de cada parceiro, derivados das pessoas que ele atendeu;
5. erros injetados nos relatos, com registro de qual erro foi aplicado a qual relato.

O gabarito de pessoas únicas sai do passo 3, antes de qualquer relato existir.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from .config import (
    CELULAS,
    FAIXAS,
    Caminhos,
    atualizar_metricas,
    carregar_gerador,
    carregar_municipios,
    carregar_quadro,
)

SETORES = ["protecao", "abrigo", "integracao", "saude"]
PESO_SETOR = np.array([0.32, 0.22, 0.24, 0.22])
FRACAO_PIN_SETOR = {"protecao": 0.55, "abrigo": 0.30, "integracao": 0.50, "saude": 0.65}
TIPOS_ORG = ["Associação", "Instituto", "Fundação", "Coletivo", "Rede", "Centro"]
ARVORES = [
    "Ipê", "Jatobá", "Aroeira", "Buriti", "Cedro", "Jacarandá", "Angico", "Sapucaia", "Copaíba",
    "Pequi", "Baru", "Andiroba", "Cumaru", "Jequitibá", "Mogno", "Oiti", "Pitanga", "Guapuruvu",
    "Embaúba", "Ingá", "Caju", "Murici", "Umbu", "Tarumã", "Bacuri", "Sibipiruna", "Canela",
]
PROB_DESFECHO = {"PRO-03": 0.45, "INT-02": 0.25}
MESES = np.arange(1, 13)


# --------------------------------------------------------------------------------------------
# 1. Parceiros e atuação
# --------------------------------------------------------------------------------------------
def gerar_parceiros(cfg: dict, muns: pd.DataFrame, rng: np.random.Generator, fake: Faker):
    peso_uf = muns.groupby("uf")["peso"].sum().sort_index()
    ufs = peso_uf.index.to_numpy()
    p_uf_local = (peso_uf**1.3 / (peso_uf**1.3).sum()).to_numpy()
    p_uf_nac = (peso_uf**0.3 / (peso_uf**0.3).sum()).to_numpy()

    parceiros, atuacao = [], []
    for i in range(cfg["n_parceiros"]):
        pid = f"P{i + 1:02d}"
        nacional = i < cfg["n_parceiros_nacionais"]
        nome = f"{TIPOS_ORG[rng.integers(len(TIPOS_ORG))]} {ARVORES[i]} {fake.last_name()}"
        if nacional:
            k = int(rng.integers(5, 9))
            ufs_p = rng.choice(ufs, size=k, replace=False, p=p_uf_nac)
            lista = [int(muns[muns.uf == u].sort_values("peso", ascending=False).iloc[0].codigo) for u in ufs_p]
            n_set = int(rng.integers(2, 4))
            uf_sede = "nacional"
        else:
            uf_sede = str(rng.choice(ufs, p=p_uf_local))
            cand = muns[muns.uf == uf_sede]
            k = min(len(cand), int(rng.integers(1, 4)))
            lista = [int(c) for c in rng.choice(cand.codigo, size=k, replace=False, p=cand.peso / cand.peso.sum())]
            n_set = 1 + int(rng.random() < 0.35)
        setores = rng.choice(SETORES, size=n_set, replace=False, p=PESO_SETOR)
        capacidade = float(rng.lognormal(0, 0.5) * (1.5 if nacional else 1.0))
        inicio = 1 if rng.random() < 0.75 else int(rng.integers(2, 6))
        parceiros.append({
            "parceiro_id": pid, "parceiro_nome": nome, "atuacao_nacional": nacional,
            "uf_sede": uf_sede, "capacidade": round(capacidade, 4), "mes_inicio": inicio,
        })
        for s in sorted(setores):
            for m in sorted(lista):
                atuacao.append({"parceiro_id": pid, "setor": s, "municipio_cod": m})

    parceiros = pd.DataFrame(parceiros).set_index("parceiro_id")
    atuacao = pd.DataFrame(atuacao)
    # Todo município do quadro de atuação precisa de ao menos um parceiro: cobre com o parceiro
    # nacional que atua em menos municípios.
    for m in muns.codigo:
        if m not in set(atuacao.municipio_cod):
            nac = parceiros[parceiros.atuacao_nacional].index
            alvo = atuacao[atuacao.parceiro_id.isin(nac)].groupby("parceiro_id").municipio_cod.nunique().idxmin()
            for s in sorted(atuacao[atuacao.parceiro_id == alvo].setor.unique()):
                atuacao.loc[len(atuacao)] = {"parceiro_id": alvo, "setor": s, "municipio_cod": int(m)}
    atuacao = atuacao.drop_duplicates().sort_values(["parceiro_id", "setor", "municipio_cod"]).reset_index(drop=True)
    atuacao = atuacao.merge(muns[["codigo", "uf"]], left_on="municipio_cod", right_on="codigo").drop(columns="codigo")
    return parceiros, atuacao


# --------------------------------------------------------------------------------------------
# 2 e 3. PIN e população sintética
# --------------------------------------------------------------------------------------------
def gerar_pin(muns: pd.DataFrame, atuacao: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    pares = atuacao[["municipio_cod", "uf", "setor"]].drop_duplicates().sort_values(["municipio_cod", "setor"])
    base = muns.set_index("codigo")["pin"]
    pin = [
        int(round(base[m] * FRACAO_PIN_SETOR[s] * rng.lognormal(0, 0.15)))
        for m, s in zip(pares.municipio_cod, pares.setor)
    ]
    return pares.assign(pin=pin).reset_index(drop=True)


def _sortear_mes(rng, n: int, inicio: int) -> np.ndarray:
    w = np.where(MESES >= inicio, 1 + 0.06 * (MESES - 1), 0.0)
    return rng.choice(MESES, size=n, p=w / w.sum())


def gerar_populacao(cfg: dict, parceiros: pd.DataFrame, atuacao: pd.DataFrame, pin: pd.DataFrame,
                    rng: np.random.Generator):
    """Devolve (pessoas, vinculos). Cada vínculo é uma pessoa atendida por um parceiro a partir de um mês."""
    p_faixa = np.array([cfg["faixas_etarias"][f] for f in FAIXAS])
    pessoas, vinculos = [], []
    prox_id = 0
    pin_idx = pin.set_index(["municipio_cod", "setor"])["pin"]
    for (s, m), grp in atuacao.groupby(["setor", "municipio_cod"], sort=True):
        P = grp.parceiro_id.to_numpy()
        cap = parceiros.loc[P, "capacidade"].to_numpy()
        ini = parceiros.loc[P, "mes_inicio"].to_numpy()
        n = int(round(pin_idx[(m, s)] * rng.uniform(cfg["cobertura_min"], cfg["cobertura_max"])))
        ids = np.arange(prox_id, prox_id + n)
        prox_id += n
        prim = rng.choice(len(P), size=n, p=cap / cap.sum())
        t0 = np.zeros(n, dtype=int)
        for j in range(len(P)):
            sel = prim == j
            t0[sel] = _sortear_mes(rng, int(sel.sum()), int(ini[j]))
        sexo = np.where(rng.random(n) < cfg["prob_feminino"], "f", "m")
        faixa = rng.choice(FAIXAS, size=n, p=p_faixa)
        pessoas.append(pd.DataFrame({
            "pessoa_id": ids, "setor": s, "municipio_cod": m, "uf": grp.uf.iloc[0],
            "sexo": sexo, "faixa": faixa, "mes": t0,
        }))
        vinculos.append(pd.DataFrame({"pessoa_id": ids, "parceiro_id": P[prim], "mes_inicio": t0}))
        if len(P) > 1:
            # Encaminhamento: a pessoa é atendida também por outro parceiro do mesmo município,
            # no mesmo mês ou até dois meses depois. Gera sobreposição dependente (não aleatória).
            enc = np.flatnonzero(rng.random(n) < cfg["prob_encaminhamento"])
            desloc = rng.integers(1, len(P), size=len(enc))
            j2 = (prim[enc] + desloc) % len(P)
            t2 = np.maximum(t0[enc] + rng.choice([0, 1, 2], size=len(enc), p=[0.5, 0.3, 0.2]), ini[j2])
            ok = t2 <= 12
            vinculos.append(pd.DataFrame({"pessoa_id": ids[enc][ok], "parceiro_id": P[j2][ok], "mes_inicio": t2[ok]}))
            if len(P) > 2:
                p3 = cfg["prob_terceiro_parceiro"] / cfg["prob_encaminhamento"]
                ter = rng.random(len(enc)) < p3
                livres = [sorted(set(range(len(P))) - {a, b}) for a, b in zip(prim[enc][ter], j2[ter])]
                j3 = np.array([lv[rng.integers(len(lv))] for lv in livres], dtype=int)
                t3 = np.maximum(t0[enc][ter] + rng.integers(1, 4, size=len(j3)), ini[j3])
                ok3 = t3 <= 12
                vinculos.append(pd.DataFrame({"pessoa_id": ids[enc][ter][ok3], "parceiro_id": P[j3][ok3],
                                              "mes_inicio": t3[ok3]}))
    pessoas = pd.concat(pessoas, ignore_index=True)
    vinculos = pd.concat(vinculos, ignore_index=True).sort_values(["pessoa_id", "mes_inicio", "parceiro_id"])
    vinculos = vinculos.reset_index(drop=True)
    vinculos["duracao"] = rng.geometric(0.45, size=len(vinculos))  # meses em abrigo (>= 1)
    for ind, p in PROB_DESFECHO.items():
        atinge = rng.random(len(vinculos)) < p
        mes_d = vinculos.mes_inicio + rng.integers(0, 4, size=len(vinculos))
        vinculos[f"desfecho_{ind}"] = np.where(atinge & (mes_d <= 12), mes_d, 0)
    return pessoas, vinculos


# --------------------------------------------------------------------------------------------
# 4. Relatos mensais dos parceiros
# --------------------------------------------------------------------------------------------
def _contar(df: pd.DataFrame, col_mes: str) -> pd.DataFrame:
    """Conta pessoas por série (parceiro, município, setor), mês e célula de desagregação."""
    out = df.assign(celula=df.sexo + "_" + df.faixa).groupby(
        ["parceiro_id", "municipio_cod", "setor", col_mes, "celula"]).size().unstack("celula", fill_value=0)
    out = out.reindex(columns=CELULAS, fill_value=0).reset_index().rename(columns={col_mes: "mes"})
    return out


def gerar_relatos(cfg: dict, quadro, parceiros: pd.DataFrame, atuacao: pd.DataFrame,
                  pessoas: pd.DataFrame, vinculos: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    ano = cfg["ano"]
    v = vinculos.merge(pessoas[["pessoa_id", "setor", "municipio_cod", "sexo", "faixa"]], on="pessoa_id")
    chave = ["parceiro_id", "municipio_cod", "setor", "mes"]

    # grade: cada série (parceiro, setor, município) relata todo mês a partir do início do parceiro
    grade = atuacao.merge(parceiros[["mes_inicio"]], left_on="parceiro_id", right_index=True)
    grade = grade.loc[grade.index.repeat(12)].assign(mes=np.tile(MESES, len(grade)))
    grade = grade[grade.mes >= grade.mes_inicio].drop(columns="mes_inicio")
    inds = quadro.indicadores.reset_index()[["indicador", "setor", "agregacao_tempo", "desagregado", "principal"]]
    grade = grade.merge(inds, on="setor").sort_values(["parceiro_id", "mes", "setor", "indicador", "municipio_cod"])

    novos = _contar(v, "mes_inicio")
    ocup = v[v.setor == "abrigo"].loc[lambda d: d.index.repeat(d.duracao)].copy()
    ocup["mes_o"] = ocup.mes_inicio + ocup.groupby(level=0).cumcount()
    estoque = _contar(ocup[ocup.mes_o <= 12], "mes_o")

    blocos = []
    for ind, df_ind in grade.groupby("indicador", sort=True):
        df_ind = df_ind.copy()
        if df_ind.principal.iloc[0]:
            df_ind = df_ind.merge(novos, on=chave, how="left")
        elif ind == "ABR-02":
            df_ind = df_ind.merge(estoque, on=chave, how="left")
        elif ind in PROB_DESFECHO:
            d = v[v[f"desfecho_{ind}"] > 0]
            mensal = _contar(d, f"desfecho_{ind}")
            df_ind = df_ind.merge(mensal, on=chave, how="left")
            df_ind[CELULAS] = df_ind[CELULAS].fillna(0)
            df_ind = df_ind.sort_values(["parceiro_id", "municipio_cod", "mes"])
            df_ind[CELULAS] = df_ind.groupby(["parceiro_id", "municipio_cod"])[CELULAS].cumsum()
        if df_ind.desagregado.iloc[0]:
            df_ind[CELULAS] = df_ind[CELULAS].fillna(0).astype(int)
            df_ind["valor"] = df_ind[CELULAS].sum(axis=1)
        else:
            base = df_ind[["parceiro_id", "municipio_cod", "setor", "mes"]].merge(
                novos.assign(n=novos[CELULAS].sum(axis=1))[chave + ["n"]], on=chave, how="left").n.fillna(0).to_numpy()
            if ind == "PRO-02":
                df_ind["valor"] = rng.poisson(0.9 * base + 1)
            elif ind == "ABR-03":
                df_ind["valor"] = rng.poisson(1.2 * base + 1)
            elif ind == "SAU-02":
                df_ind["valor"] = rng.poisson(2.5 * base + 3)
            elif ind == "SAU-03":
                serie = df_ind.groupby(["parceiro_id", "municipio_cod"]).ngroup().to_numpy()
                n_s = serie.max() + 1
                k = rng.integers(1, 4, size=n_s)
                mes_amplia = rng.integers(3, 13, size=n_s)
                df_ind["valor"] = (k[serie] + (df_ind.mes.to_numpy() >= mes_amplia[serie])
                                   - (rng.random(len(df_ind)) < 0.15)).clip(0)
            if ind != "SAU-03":
                # picos legítimos (mutirão, campanha): não são erro, mas parecem outlier
                campanha = rng.random(len(df_ind)) < 0.02
                df_ind.loc[campanha, "valor"] = df_ind.loc[campanha, "valor"] * rng.integers(3, 9, campanha.sum())
            for c in CELULAS:
                df_ind[c] = np.nan
        blocos.append(df_ind)

    ordem = ["parceiro_id", "mes", "setor", "indicador", "municipio_cod"]
    rel = pd.concat(blocos, ignore_index=True).sort_values(ordem)
    rel = rel.reset_index(drop=True)
    prazo = [date(ano + (m == 12), 1 if m == 12 else m + 1, cfg["prazo_dia"]) for m in rel.mes]
    antecedencia = rng.integers(0, cfg["prazo_dia"], size=len(rel))
    rel["data_envio"] = [p - timedelta(days=int(a)) for p, a in zip(prazo, antecedencia)]
    rel["mes"] = [f"{ano}-{m:02d}" for m in rel.mes]
    rel = rel.merge(parceiros[["parceiro_nome"]], left_on="parceiro_id", right_index=True)
    return rel[["parceiro_id", "parceiro_nome", "mes", "uf", "municipio_cod", "setor", "indicador", "valor",
                *CELULAS, "data_envio"]].reset_index(drop=True)


# --------------------------------------------------------------------------------------------
# 5. Erros injetados
# --------------------------------------------------------------------------------------------
def injetar_erros(rel: pd.DataFrame, cfg: dict, quadro, muns_ref: pd.DataFrame, muns_atuacao: pd.DataFrame,
                  rng: np.random.Generator):
    taxas = cfg["erros"]
    rel = rel.copy()
    rel["tipo_erro"] = ""
    ind = quadro.indicadores
    soma = rel.indicador.map(ind.agregacao_tempo).eq("soma")
    desag = rel.indicador.map(ind.desagregado).astype(bool)

    # acumulado informado como mensal: a série inteira passa a vir acumulada
    series = rel[soma].groupby(["parceiro_id", "municipio_cod", "indicador"])
    elegiveis = [k for k, g in series if len(g) >= 8 and (g.valor > 0).sum() >= 5]
    n_ac = max(1, round(taxas["acumulado_como_mensal"] * series.ngroups))
    escolhidas = [elegiveis[i] for i in sorted(rng.choice(len(elegiveis), size=n_ac, replace=False))]
    for k in escolhidas:
        idx = series.get_group(k).sort_values("mes").index
        cols = ["valor"] + (CELULAS if desag[idx[0]] else [])
        # metade das séries vem acumulada o ano todo; a outra metade passa a vir acumulada no meio
        # do ano (troca do responsável pelo relato). Só os meses afetados contam como erro.
        inicio = 0 if rng.random() < 0.5 else int(rng.integers(3, len(idx) - 3))
        acumulado = rel.loc[idx, cols].cumsum()
        rel.loc[idx[inicio:], cols] = acumulado.loc[idx[inicio:]]
        rel.loc[idx[inicio:], "tipo_erro"] = "acumulado_como_mensal"

    livres = list(rng.permutation(rel.index[rel.tipo_erro == ""]))
    n = len(rel)

    def tomar(qtd: int, cond) -> list[int]:
        out = []
        for i in list(livres):
            if len(out) == qtd:
                break
            if cond(rel.loc[i]):
                out.append(i)
                livres.remove(i)
        return out

    validos = set(muns_ref.codigo_ibge)
    for i in tomar(round(taxas["municipio_invalido"] * n), lambda r: True):
        cod = int(rel.at[i, "municipio_cod"])
        novo = cod // 10 if rng.random() < 0.5 else next(
            c for c in (cod - cod % 10 + d for d in rng.permutation(10)) if c not in validos)
        rel.loc[i, ["municipio_cod", "tipo_erro"]] = [novo, "municipio_invalido"]

    atua = rel.groupby("parceiro_id").municipio_cod.agg(set)
    for i in tomar(round(taxas["municipio_fora_uf"] * n), lambda r: True):
        r = rel.loc[i]
        cand = muns_atuacao[(muns_atuacao.uf != r.uf) & ~muns_atuacao.codigo.isin(atua[r.parceiro_id])].codigo
        rel.loc[i, ["municipio_cod", "tipo_erro"]] = [int(rng.choice(cand)), "municipio_fora_uf"]

    for i in tomar(round(taxas["desagregacao_inconsistente"] * n), lambda r: desag[r.name] and r.valor >= 2):
        c = CELULAS[rng.integers(len(CELULAS))]
        if rng.random() < 0.3:
            rel.at[i, c] = np.nan
        else:
            delta = int(rng.integers(1, 4))
            rel.at[i, c] = rel.at[i, c] + delta if rel.at[i, c] < delta or rng.random() < 0.5 else rel.at[i, c] - delta
        rel.at[i, "tipo_erro"] = "desagregacao_inconsistente"

    for i in tomar(round(taxas["indicador_fora_do_quadro"] * n), lambda r: True):
        cod = rel.at[i, "indicador"]
        pre = cod.split("-")[0]
        prox = ind[ind.index.str.startswith(pre)].shape[0] + 1
        rel.loc[i, ["indicador", "tipo_erro"]] = [cod.replace("-", "") if rng.random() < 0.5 else f"{pre}-{prox:02d}",
                                                  "indicador_fora_do_quadro"]

    for i in tomar(round(taxas["valor_implausivel"] * n), lambda r: r.valor >= 1):
        cols = ["valor"] + (CELULAS if desag[i] else [])
        rel.loc[i, cols] = rel.loc[i, cols] * int(rng.choice([10, 100]))  # um ou dois zeros a mais
        rel.at[i, "tipo_erro"] = "valor_implausivel"

    ano = cfg["ano"]
    for i in tomar(round(taxas["fora_do_prazo"] * n), lambda r: True):
        m = int(rel.at[i, "mes"][-2:])
        prazo = date(ano + (m == 12), 1 if m == 12 else m + 1, cfg["prazo_dia"])
        rel.loc[i, ["data_envio", "tipo_erro"]] = [prazo + timedelta(days=int(rng.integers(1, 46))), "fora_do_prazo"]

    origens = tomar(round(taxas["relato_duplicado"] * n), lambda r: True)
    copias = rel.loc[origens].copy()
    copias["tipo_erro"] = "relato_duplicado"
    rel = pd.concat([rel, copias], ignore_index=True)

    rel = rel.sort_values("data_envio", kind="mergesort").reset_index(drop=True)
    rel.insert(0, "relato_id", [f"R{i + 1:05d}" for i in range(len(rel))])
    erros = rel.loc[rel.tipo_erro != "", ["relato_id", "tipo_erro"]].reset_index(drop=True)
    return rel.drop(columns="tipo_erro"), erros


# --------------------------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------------------------
def executar(caminhos: Caminhos | None = None) -> dict:
    c = caminhos or Caminhos()
    c.garantir()
    cfg = carregar_gerador(c)
    quadro = carregar_quadro(c)
    rng = np.random.default_rng(cfg["semente"])
    Faker.seed(cfg["semente"])
    fake = Faker("pt_BR")

    ref = carregar_municipios(c)
    muns = pd.DataFrame(cfg["municipios"]).merge(ref, left_on="codigo", right_on="codigo_ibge", validate="1:1")

    parceiros, atuacao = gerar_parceiros(cfg, muns, rng, fake)
    pin = gerar_pin(muns, atuacao, rng)
    pessoas, vinculos = gerar_populacao(cfg, parceiros, atuacao, pin, rng)
    relatos_limpos = gerar_relatos(cfg, quadro, parceiros, atuacao, pessoas, vinculos, rng)
    relatos, erros = injetar_erros(relatos_limpos, cfg, quadro, ref, muns[["codigo", "uf"]], rng)

    gabarito = (pessoas.groupby(["setor", "uf", "municipio_cod", "mes"]).size().rename("pessoas_unicas").reset_index())
    gabarito["mes"] = [f"{cfg['ano']}-{m:02d}" for m in gabarito.mes]

    for df in (relatos, relatos_limpos):
        df[CELULAS] = df[CELULAS].astype("Int64")
        df["valor"] = df["valor"].astype("int64")
    parceiros.reset_index().to_csv(c.sintetico / "parceiros.csv", index=False)
    atuacao.to_csv(c.sintetico / "atuacao.csv", index=False)
    pin.to_csv(c.sintetico / "pin.csv", index=False)
    relatos.to_csv(c.sintetico / "relatos.csv", index=False)
    relatos_limpos.to_csv(c.sintetico / "relatos_sem_erros.csv", index=False)
    erros.to_csv(c.sintetico / "erros_injetados.csv", index=False)
    gabarito.to_csv(c.sintetico / "gabarito_pessoas_unicas.csv", index=False)

    multi = vinculos.groupby("pessoa_id").size()
    metricas = {
        "parceiros": int(len(parceiros)),
        "ufs": int(atuacao.uf.nunique()),
        "municipios": int(atuacao.municipio_cod.nunique()),
        "pessoas_unicas": int(len(pessoas)),
        "vinculos_pessoa_parceiro": int(len(vinculos)),
        "pct_pessoas_com_mais_de_um_parceiro": round(100 * float((multi > 1).mean()), 2),
        "relatos": int(len(relatos)),
        "relatos_com_erro_injetado": int(len(erros)),
        "pct_relatos_com_erro_injetado": round(100 * len(erros) / len(relatos), 2),
        "erros_injetados_por_tipo": {k: int(v) for k, v in erros.tipo_erro.value_counts().sort_index().items()},
    }
    atualizar_metricas("geracao", metricas, c)
    return metricas
