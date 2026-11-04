"""Calcula o risco de cheia para um dia e registra a previsão no banco (usuário svc_modelo)."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .. import config
from ..coleta.ana import ESTACOES
from .dados import VARIAVEIS, construir_variaveis
from .treinar import carregar_modelo

JANELA_DIAS = 10


class DadosInsuficientes(Exception):
    pass


def nivel_de_risco(p):
    if p >= config.CORTE_ALTO:
        return "alto"
    if p >= config.CORTE_MEDIO:
        return "medio"
    return "baixo"


def _janela_mongo(banco, dia):
    inicio = datetime.combine(dia - timedelta(days=JANELA_DIAS), datetime.min.time())
    fim = datetime.combine(dia, datetime.min.time())
    cursor = banco.series_hidrologicas.find(
        {"estacao_id": {"$in": list(ESTACOES)}, "data_hora": {"$gte": inicio, "$lte": fim},
         "fonte": {"$in": ["ANA", "ANA-telemetria"]}},
        {"_id": 0, "estacao_id": 1, "data_hora": 1, "vazao_m3s": 1, "chuva_mm": 1})
    linhas = []
    for r in cursor:
        tipo = ESTACOES[r["estacao_id"]]["tipo"]
        linhas.append((r["data_hora"], f"{tipo}_{r['estacao_id']}",
                       r.get("vazao_m3s") if tipo == "vazao" else r.get("chuva_mm")))
    if not linhas:
        raise DadosInsuficientes(f"não há leituras da ANA no banco entre {inicio.date()} e {fim.date()}")
    df = pd.DataFrame(linhas, columns=["data", "coluna", "valor"])
    df["data"] = pd.to_datetime(df["data"]).dt.normalize()
    tabela = df.pivot_table(index="data", columns="coluna", values="valor", aggfunc="mean")
    return tabela.reindex(pd.date_range(inicio, fim, freq="D"))


def _janela_csv(dia):
    tabela = pd.read_csv(config.PASTA_PROCESSADOS / "serie_diaria.csv", index_col="data", parse_dates=True)
    return tabela.loc[pd.Timestamp(dia - timedelta(days=JANELA_DIAS)): pd.Timestamp(dia)]


def explicar(pacote, linha):
    """Na regressão logística, mostra quanto cada variável empurrou a probabilidade (beta x valor)."""
    modelo = pacote["modelo"]
    if not hasattr(modelo, "named_steps"):
        return None
    z = modelo.named_steps["escala"].transform(linha[VARIAVEIS])[0]
    betas = modelo.named_steps["modelo"].coef_[0]
    contrib = {v: round(float(b * x), 3) for v, b, x in zip(VARIAVEIS, betas, z)}
    return dict(sorted(contrib.items(), key=lambda kv: -abs(kv[1]))[:4])


def prever(dia, fonte="mongo", registrar=True, modo=None):
    if isinstance(dia, str):
        dia = datetime.strptime(dia, "%Y-%m-%d").date()
    pacote = carregar_modelo()
    if fonte == "mongo":
        from ..db import conectar
        banco = conectar("modelo")
        janela = _janela_mongo(banco, dia)
    else:
        banco = None
        janela = _janela_csv(dia)

    variaveis = construir_variaveis(janela)
    alvo = pd.Timestamp(dia)
    if alvo not in variaveis.index:
        raise DadosInsuficientes(f"sem dados para {dia}")
    linha = variaveis.loc[[alvo]]
    faltando = [v for v in VARIAVEIS if pd.isna(linha[v].iloc[0])]
    if faltando:
        raise DadosInsuficientes(f"faltam dados em {dia} para: {', '.join(faltando)}")

    p = float(pacote["modelo"].predict_proba(linha[VARIAVEIS])[0, 1])
    resultado = {
        "data_referencia": dia.isoformat(),
        "probabilidade": round(p, 4),
        "nivel_risco": nivel_de_risco(p),
        "versao_modelo": pacote["versao"],
        "estacao_id": config.ESTACAO_ALVO,
        "limiar_m3s": round(float(pacote["limiar_m3s"]), 1),
        "vazao_atual_m3s": round(float(linha["vazao_m3s"].iloc[0]), 1),
        "chuva72_mm": round(float(linha["chuva72_mm"].iloc[0]), 1),
        "postos_chuva": int(linha["postos_chuva"].iloc[0]),
        "contribuicoes": explicar(pacote, linha),
        "modo": modo or config.MODO_OPERACAO,
    }
    if registrar and banco is not None:
        doc = {
            "data_hora": datetime.now(timezone.utc),
            "data_referencia": datetime.combine(dia, datetime.min.time()),
            "probabilidade": resultado["probabilidade"],
            "nivel_risco": resultado["nivel_risco"],
            "versao_modelo": resultado["versao_modelo"],
            "estacao_id": resultado["estacao_id"],
            "limiar_m3s": resultado["limiar_m3s"],
            "variaveis": {"vazao_m3s": resultado["vazao_atual_m3s"], "chuva72_mm": resultado["chuva72_mm"],
                          "postos_chuva": resultado["postos_chuva"]},
            "modo": resultado["modo"],
        }
        resultado["previsao_id"] = str(banco.previsoes.insert_one(doc).inserted_id)
        banco.auditoria.insert_one({"data_hora": datetime.now(timezone.utc), "usuario": config.USUARIOS["modelo"],
                                    "acao": "insert", "colecao": "previsoes", "ip": "127.0.0.1",
                                    "detalhe": f"previsão {dia} nível {resultado['nivel_risco']} p={p:.3f}"})
    return resultado


if __name__ == "__main__":  # pragma: no cover
    import sys
    print(prever(sys.argv[1], fonte="csv", registrar=False))
