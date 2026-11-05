"""Treino e avaliação do modelo de previsão de cheia.

Divisão no tempo: treina com os anos antes de ANO_CORTE_TREINO e testa nos anos seguintes,
que o modelo nunca viu. Compara com a regra de referência "amanhã igual a hoje" (persistência).
"""
import json
from datetime import date

import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .. import config
from . import limiares
from .dados import VARIAVEIS, carregar_tabela, conjunto_de_treino, eventos

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

ARQUIVO_MODELO = config.PASTA_MODELOS / "modelo_risco.joblib"


def novos_modelos():
    return {
        "regressao_logistica": Pipeline([
            ("escala", StandardScaler()),
            ("modelo", LogisticRegression(class_weight="balanced", max_iter=5000)),
        ]),
        "random_forest": RandomForestClassifier(
            n_estimators=400, min_samples_leaf=5, class_weight="balanced_subsample",
            random_state=42, n_jobs=-1),
    }


def metricas(y, p, corte):
    previsto = (p >= corte).astype(int)
    vp = int(((previsto == 1) & (y == 1)).sum())
    fp = int(((previsto == 1) & (y == 0)).sum())
    fn = int(((previsto == 0) & (y == 1)).sum())
    vn = int(((previsto == 0) & (y == 0)).sum())
    return {
        "corte": corte,
        "recall": round(recall_score(y, previsto, zero_division=0), 3),
        "precisao": round(precision_score(y, previsto, zero_division=0), 3),
        "f1": round(f1_score(y, previsto, zero_division=0), 3),
        "vp": vp, "fp": fp, "fn": fn, "vn": vn,
    }


def avaliar(y, p, anos):
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    saida = {
        "brier": round(float(brier_score_loss(y, p)), 4),
        "pr_auc": round(float(average_precision_score(y, p)), 3) if y.sum() else None,
        "medio": metricas(y, p, config.CORTE_MEDIO),
        "alto": metricas(y, p, config.CORTE_ALTO),
    }
    saida["alarmes_falsos_por_ano"] = round(saida["medio"]["fp"] / max(anos, 1), 1)
    return saida


def avaliar_eventos(prob, serie_q, limiar, corte):
    """Um evento conta como avisado se o modelo passou do corte no dia anterior ao início da cheia."""
    resultado = []
    for e in eventos(serie_q, limiar):
        inicio = pd.Timestamp(e["inicio"])
        vespera = inicio - pd.Timedelta(days=1)
        p_vespera = prob.get(vespera)
        antecedencia = 0
        for k in range(1, 4):
            pk = prob.get(inicio - pd.Timedelta(days=k))
            if pk is None or pk < corte:
                break
            antecedencia = k
        resultado.append({**{k: str(v) for k, v in e.items() if k in ("inicio", "fim", "dia_pico")},
                          "pico_m3s": round(e["pico_m3s"], 1), "tr_anos": e["tr_anos"], "dias": e["dias"],
                          "p_vespera": None if p_vespera is None else round(float(p_vespera), 3),
                          "avisado": bool(p_vespera is not None and p_vespera >= corte),
                          "antecedencia_dias": antecedencia})
    return resultado


def _figura_serie(tabela, limiar, corte, pasta):
    q = tabela[f"vazao_{config.ESTACAO_ALVO}"]
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(q.index, q.values, lw=0.6, color="#1f5c8a")
    for valor, nome, cor in [(limiares.vazao_para_tr(2), "TR 2 anos", "#8fb3d1"),
                             (limiar, f"limiar do modelo, TR {config.TR_ALVO:g} anos", "#d98a2b"),
                             (limiares.TABELA_UESC_CONTORNO[54][0], "TR 54 anos (UESC)", "#b32d2d")]:
        ax.axhline(valor, color=cor, ls="--", lw=1, label=f"{nome}: {valor:.0f} m³/s")
    ax.axvline(corte, color="#555", lw=1, ls=":")
    ax.text(corte, ax.get_ylim()[1] * 0.95, " início do teste", fontsize=8, va="top")
    ax.set_ylabel("vazão média diária (m³/s)")
    ax.set_title("Rio Cachoeira, estação Contorno da BR-101 (53180000), dados da ANA")
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(pasta / "serie_contorno.png", dpi=150)
    plt.close(fig)


def _figura_evento(dados, prob, evento, limiar, pasta):
    inicio = pd.Timestamp(evento["inicio"])
    janela = dados.loc[inicio - pd.Timedelta(days=10): inicio + pd.Timedelta(days=5)]
    if janela.empty:
        return None
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(janela.index, janela["chuva72_mm"], color="#9cc3e6", label="chuva acumulada em 72 h (mm)")
    ax.set_ylabel("chuva em 72 h (mm)")
    ax2 = ax.twinx()
    ax2.plot(janela.index, janela["vazao_m3s"], color="#1f5c8a", marker="o", ms=3, label="vazão (m³/s)")
    ax2.axhline(limiar, color="#d98a2b", ls="--", lw=1)
    ax2.set_ylabel("vazão (m³/s)")
    ax3 = ax.twinx()
    ax3.spines["right"].set_position(("outward", 55))
    p = prob.reindex(janela.index)
    ax3.plot(janela.index, p, color="#b32d2d", marker="s", ms=3, label="probabilidade de cheia em 24 h")
    ax3.axhline(config.CORTE_MEDIO, color="#b32d2d", ls=":", lw=0.8)
    ax3.set_ylim(0, 1)
    ax3.set_ylabel("probabilidade")
    linhas = [h for a in (ax, ax2, ax3) for h in a.get_legend_handles_labels()[0]]
    nomes = [n for a in (ax, ax2, ax3) for n in a.get_legend_handles_labels()[1]]
    ax.legend(linhas, nomes, fontsize=7, loc="upper left")
    ax.set_title(f"Cheia de {evento['inicio']}: pico de {evento['pico_m3s']:.0f} m³/s")
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    nome = f"evento_{evento['inicio']}.png"
    fig.savefig(pasta / nome, dpi=150)
    plt.close(fig)
    return nome


def treinar(fonte="csv", avisar=print):
    pasta = config.PASTA_RESULTADOS / "modelo"
    pasta.mkdir(parents=True, exist_ok=True)
    config.PASTA_MODELOS.mkdir(parents=True, exist_ok=True)

    tabela = carregar_tabela(fonte)
    limiar = limiares.vazao_para_tr(config.TR_ALVO)
    dados = conjunto_de_treino(tabela, limiar)
    corte = pd.Timestamp(f"{config.ANO_CORTE_TREINO}-01-01")
    treino, teste = dados[dados.index < corte], dados[dados.index >= corte]
    if treino.y.sum() < 3:
        raise RuntimeError(f"o treino tem só {int(treino.y.sum())} dias de cheia; confira os dados baixados")
    anos_teste = (teste.index.max() - teste.index.min()).days / 365.25 if len(teste) else 0

    avisar(f"Limiar do modelo: {limiar:.0f} m³/s (TR de {config.TR_ALVO:g} anos, estudo da UESC)")
    avisar(f"Treino: {treino.index.min().date()} a {treino.index.max().date()} | {len(treino)} dias, "
           f"{int(treino.y.sum())} com cheia no dia seguinte")
    avisar(f"Teste:  {teste.index.min().date()} a {teste.index.max().date()} | {len(teste)} dias, "
           f"{int(teste.y.sum())} com cheia no dia seguinte")

    q_teste = tabela[f"vazao_{config.ESTACAO_ALVO}"].loc[corte:]
    resultados, probs = {}, {}

    p_pers = (teste["vazao_m3s"] >= limiar).astype(float)
    probs["persistencia"] = p_pers
    resultados["persistencia"] = {**avaliar(teste.y, p_pers, anos_teste),
                                  "eventos": avaliar_eventos(p_pers, q_teste, limiar, config.CORTE_MEDIO)}

    for nome, modelo in novos_modelos().items():
        modelo.fit(treino[VARIAVEIS], treino.y.astype(int))
        p = pd.Series(modelo.predict_proba(teste[VARIAVEIS])[:, 1], index=teste.index)
        probs[nome] = p
        resultados[nome] = {**avaliar(teste.y, p, anos_teste),
                            "eventos": avaliar_eventos(p, q_teste, limiar, config.CORTE_MEDIO)}

    for nome, r in resultados.items():
        ev = r["eventos"]
        r["eventos_avisados"] = f"{sum(e['avisado'] for e in ev)}/{len(ev)}"
        avisar(f"{nome:>20}: recall {r['medio']['recall']:.2f} | precisão {r['medio']['precisao']:.2f} | "
               f"F1 {r['medio']['f1']:.2f} | Brier {r['brier']:.4f} | eventos avisados na véspera {r['eventos_avisados']}")

    def chave(nome):
        r = resultados[nome]
        avisados = sum(e["avisado"] for e in r["eventos"])
        return (avisados, r["medio"]["f1"], -r["brier"])
    escolhido = max(["regressao_logistica", "random_forest"], key=chave)
    avisar(f"Modelo escolhido: {escolhido}")

    lr = novos_modelos()["regressao_logistica"].fit(treino[VARIAVEIS], treino.y.astype(int))
    coef = pd.DataFrame({"variavel": VARIAVEIS, "beta": lr.named_steps["modelo"].coef_[0]})
    coef.loc[len(coef)] = ["intercepto (beta0)", lr.named_steps["modelo"].intercept_[0]]
    coef.to_csv(pasta / "coeficientes_regressao_logistica.csv", index=False, float_format="%.4f")

    # depois de avaliado, o modelo escolhido é treinado de novo com todos os anos para operar
    final = novos_modelos()[escolhido].fit(dados[VARIAVEIS], dados.y.astype(int))
    versao = f"{escolhido}-{date.today().isoformat()}"
    joblib.dump({"modelo": final, "nome": escolhido, "versao": versao, "variaveis": VARIAVEIS,
                 "limiar_m3s": limiar, "tr_alvo": config.TR_ALVO,
                 "cortes": {"medio": config.CORTE_MEDIO, "alto": config.CORTE_ALTO}}, ARQUIVO_MODELO)

    _figura_serie(tabela, limiar, corte, pasta)
    figuras = ["serie_contorno.png"]
    ev_teste = resultados[escolhido]["eventos"]
    if ev_teste:
        maior = max(ev_teste, key=lambda e: e["pico_m3s"])
        nome_fig = _figura_evento(teste, probs[escolhido], maior, limiar, pasta)
        if nome_fig:
            figuras.append(nome_fig)

    pd.DataFrame(ev_teste).to_csv(pasta / "eventos_teste.csv", index=False)
    resumo = {
        "gerado_em": date.today().isoformat(),
        "fonte_dados": "ANA (Hidroweb), estações do estudo de Farias e Gomes (2023)",
        "estacao_alvo": config.ESTACAO_ALVO,
        "limiar_m3s": round(limiar, 1),
        "tr_alvo_anos": config.TR_ALVO,
        "gumbel_uesc": {"u": round(limiares.U, 1), "alfa": round(limiares.ALFA, 1)},
        "periodo_treino": [str(treino.index.min().date()), str(treino.index.max().date())],
        "periodo_teste": [str(teste.index.min().date()), str(teste.index.max().date())],
        "dias_treino": len(treino), "dias_cheia_treino": int(treino.y.sum()),
        "dias_teste": len(teste), "dias_cheia_teste": int(teste.y.sum()),
        "variaveis": VARIAVEIS,
        "resultados": resultados,
        "modelo_escolhido": escolhido,
        "versao_modelo": versao,
        "figuras": figuras,
    }
    (pasta / "metricas.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    avisar(f"Resultados salvos em {pasta}")
    return resumo


def carregar_modelo():
    if not ARQUIVO_MODELO.exists():
        raise FileNotFoundError("modelo não treinado. Rode: python cli.py treinar")
    return joblib.load(ARQUIVO_MODELO)
