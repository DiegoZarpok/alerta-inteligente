"""Classificação dos relatos dos moradores (usuário svc_classificador).

Usa o BERTimbau ajustado no Colab, se a pasta modelos/bertimbau_relatos existir. Enquanto ele não
estiver na máquina, usa o modelo de comparação TF-IDF + regressão logística treinado nos mesmos dados.
O classificador só lê o texto anonimizado (view vw_relatos_anonimizados).
"""
from datetime import datetime, timezone

import pandas as pd

from .. import config

PASTA_BERT = config.PASTA_MODELOS / "bertimbau_relatos"
CLASSES = ["confirmado", "observacao", "nao_relacionado"]


class Classificador:
    def __init__(self):
        if (PASTA_BERT / "config.json").exists():
            from transformers import pipeline
            self.nome = "bertimbau-ajustado"
            self._pipe = pipeline("text-classification", model=str(PASTA_BERT), tokenizer=str(PASTA_BERT))
        else:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import make_pipeline
            dados = pd.read_csv(config.PASTA_RELATOS / "relatos.csv")
            treino = dados[dados.divisao == "treino"]
            self.nome = "tfidf-regressao-logistica"
            self._pipe = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True),
                                       LogisticRegression(max_iter=2000, class_weight="balanced"))
            self._pipe.fit(treino.texto, treino.classe)

    def prever(self, textos):
        if self.nome == "bertimbau-ajustado":
            return [r["label"] for r in self._pipe(list(textos), truncation=True)]
        return list(self._pipe.predict(list(textos)))


def classificar_pendentes(avisar=print):
    from ..db import conectar
    banco = conectar("classificador")
    pendentes = list(banco.vw_relatos_anonimizados.find({"classe": None}, {"_id": 1, "texto_anonimizado": 1}))
    if not pendentes:
        avisar("Nenhum relato pendente.")
        return 0
    modelo = Classificador()
    classes = modelo.prever([p["texto_anonimizado"] for p in pendentes])
    for p, c in zip(pendentes, classes):
        banco.relatos.update_one({"_id": p["_id"]}, {"$set": {"classe": c, "classificado_por": modelo.nome}})
    banco.auditoria.insert_one({"data_hora": datetime.now(timezone.utc), "usuario": config.USUARIOS["classificador"],
                                "acao": "update", "colecao": "relatos", "ip": "127.0.0.1",
                                "detalhe": f"{len(pendentes)} relatos classificados com {modelo.nome}"})
    avisar(f"{len(pendentes)} relatos classificados com {modelo.nome}")
    return len(pendentes)
