"""Monta a tabela diária, as variáveis de entrada e o alvo do modelo."""
import numpy as np
import pandas as pd

from .. import config
from ..coleta.ana import ESTACOES
from . import limiares

VARIAVEIS = [
    "chuva24", "chuva48", "chuva72",          # chuva média da bacia acumulada (mm, escala log)
    "vazao", "delta_vazao", "media_movel_7d",  # Contorno da BR-101 (m³/s, escala log)
    "vazao_ferradas", "delta_ferradas",        # Ferradas, a montante
    "mes_sen", "mes_cos",                      # mês do ano em forma cíclica
]
MIN_POSTOS_CHUVA = 2


def colunas_chuva(tabela):
    return [c for c in tabela.columns if c.startswith("chuva_")]


def _log(x):
    return np.log1p(np.clip(x, 0, None))


def _log_com_sinal(x):
    return np.sign(x) * np.log1p(np.abs(x))


def construir_variaveis(tabela, alvo=config.ESTACAO_ALVO, montante="53170000"):
    """Recebe a tabela diária (data, vazao_<cod>, chuva_<cod>) e devolve as variáveis do dia t."""
    t = tabela.sort_index().asfreq("D")
    chuvas = t[colunas_chuva(t)]
    postos = chuvas.notna().sum(axis=1)
    chuva_media = chuvas.mean(axis=1).where(postos >= MIN_POSTOS_CHUVA)

    q = t[f"vazao_{alvo}"]
    qf = t.get(f"vazao_{montante}", pd.Series(np.nan, index=t.index))

    v = pd.DataFrame(index=t.index)
    v["chuva24"] = _log(chuva_media)
    v["chuva48"] = _log(chuva_media.rolling(2, min_periods=2).sum())
    v["chuva72"] = _log(chuva_media.rolling(3, min_periods=3).sum())
    v["vazao"] = _log(q)
    v["delta_vazao"] = _log_com_sinal(q.diff())
    v["media_movel_7d"] = _log(q.rolling(7, min_periods=5).mean())
    v["vazao_ferradas"] = _log(qf)
    v["delta_ferradas"] = _log_com_sinal(qf.diff())
    mes = t.index.month
    v["mes_sen"] = np.sin(2 * np.pi * mes / 12)
    v["mes_cos"] = np.cos(2 * np.pi * mes / 12)

    # valores originais, para relatórios e mensagens
    v["vazao_m3s"] = q
    v["chuva72_mm"] = chuva_media.rolling(3, min_periods=3).sum()
    v["postos_chuva"] = postos
    return v


def construir_alvo(tabela, limiar=None, alvo=config.ESTACAO_ALVO):
    """y(t) = 1 se a vazão média do dia seguinte passar do limiar (padrão: TR de 3 anos)."""
    limiar = limiar or limiares.vazao_para_tr(config.TR_ALVO)
    q = tabela.sort_index().asfreq("D")[f"vazao_{alvo}"]
    amanha = q.shift(-1)
    y = (amanha >= limiar).astype("float")
    y[amanha.isna()] = np.nan
    return y, amanha


def conjunto_de_treino(tabela, limiar=None):
    v = construir_variaveis(tabela)
    y, amanha = construir_alvo(tabela, limiar)
    dados = v.assign(y=y, vazao_amanha=amanha).dropna(subset=VARIAVEIS + ["y"])
    return dados


def eventos(serie_vazao, limiar):
    """Agrupa dias seguidos acima do limiar em eventos de cheia."""
    acima = serie_vazao >= limiar
    lista, inicio = [], None
    for dia, flag in acima.items():
        if flag and inicio is None:
            inicio = dia
        elif not flag and inicio is not None:
            trecho = serie_vazao[inicio:dia - pd.Timedelta(days=1)]
            lista.append({"inicio": inicio.date(), "fim": trecho.index[-1].date(),
                          "pico_m3s": float(trecho.max()), "dia_pico": trecho.idxmax().date(),
                          "dias": len(trecho)})
            inicio = None
    if inicio is not None:
        trecho = serie_vazao[inicio:]
        lista.append({"inicio": inicio.date(), "fim": trecho.index[-1].date(), "pico_m3s": float(trecho.max()),
                      "dia_pico": trecho.idxmax().date(), "dias": len(trecho)})
    for e in lista:
        e["tr_anos"] = round(limiares.tr_da_vazao(e["pico_m3s"]), 1)
    return lista


def carregar_tabela(fonte="csv"):
    """Lê a série diária do CSV processado ou do MongoDB (usuário svc_modelo)."""
    if fonte == "csv":
        caminho = config.PASTA_PROCESSADOS / "serie_diaria.csv"
        if not caminho.exists():
            raise FileNotFoundError("dados/processados/serie_diaria.csv não existe. Rode: python cli.py baixar-dados")
        return pd.read_csv(caminho, index_col="data", parse_dates=True)
    from ..db import conectar
    banco = conectar("modelo")
    registros = banco.series_hidrologicas.find(
        {"fonte": {"$in": ["ANA", "ANA-telemetria"]}, "estacao_id": {"$in": list(ESTACOES)}},
        {"_id": 0, "estacao_id": 1, "data_hora": 1, "vazao_m3s": 1, "chuva_mm": 1})
    linhas = []
    for r in registros:
        tipo = ESTACOES[r["estacao_id"]]["tipo"]
        valor = r.get("vazao_m3s") if tipo == "vazao" else r.get("chuva_mm")
        linhas.append((r["data_hora"], f"{tipo}_{r['estacao_id']}", valor))
    if not linhas:
        raise RuntimeError("series_hidrologicas está vazia. Rode: python cli.py carregar-dados")
    df = pd.DataFrame(linhas, columns=["data", "coluna", "valor"])
    df["data"] = pd.to_datetime(df["data"]).dt.normalize()
    tabela = df.pivot_table(index="data", columns="coluna", values="valor", aggfunc="mean")
    return tabela.asfreq("D")
