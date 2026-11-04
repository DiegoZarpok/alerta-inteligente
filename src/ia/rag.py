"""RAG: divide os 24 documentos em trechos, guarda os vetores no MongoDB e busca os mais parecidos."""
import re
import time
from datetime import datetime, timezone

import numpy as np

from .. import config
from . import embeddings

PALAVRAS_POR_TOKEN = 1 / 1.3  # estimativa simples para português: 1 palavra ~ 1,3 token
MAX_TOKENS = 400
SOBREPOSICAO_TOKENS = 50


def ler_documento(caminho):
    texto = caminho.read_text(encoding="utf-8")
    titulo = re.search(r"^# (.+)$", texto, re.M).group(1).strip()
    tipo = re.search(r"^> Tipo: (.+?)\s*$", texto, re.M).group(1).strip()
    niveis_txt = re.search(r"^> Nível: (.+?)\s*$", texto, re.M)
    niveis = [n.strip() for n in (niveis_txt.group(1) if niveis_txt else "todos").split(",")]
    corpo = "\n".join(l for l in texto.splitlines() if not l.startswith("#") and not l.startswith(">")).strip()
    return {"arquivo": caminho.name, "titulo": titulo, "tipo": tipo, "niveis": niveis, "corpo": corpo}


def dividir(corpo, max_tokens=MAX_TOKENS, sobreposicao=SOBREPOSICAO_TOKENS):
    """Divide por seções (parágrafos e listas), juntando blocos até ~400 tokens, com 50 de sobreposição."""
    max_palavras = int(max_tokens * PALAVRAS_POR_TOKEN)
    sobra = int(sobreposicao * PALAVRAS_POR_TOKEN)
    blocos = [b.strip() for b in re.split(r"\n\s*\n", corpo) if b.strip()]
    trechos, atual = [], []
    for bloco in blocos:
        palavras = bloco.split()
        if atual and len(atual) + len(palavras) > max_palavras:
            trechos.append(" ".join(atual))
            atual = atual[-sobra:]
        atual.extend(palavras)
        while len(atual) > max_palavras:  # bloco maior que o limite
            trechos.append(" ".join(atual[:max_palavras]))
            atual = atual[max_palavras - sobra:]
    if atual:
        trechos.append(" ".join(atual))
    return trechos


def preparar_trechos(pasta=None):
    pasta = pasta or config.PASTA_DOCUMENTOS
    trechos = []
    for caminho in sorted(pasta.glob("[0-9][0-9]_*.md")):
        doc = ler_documento(caminho)
        for i, texto in enumerate(dividir(doc["corpo"])):
            trechos.append({"arquivo": doc["arquivo"], "titulo": doc["titulo"], "tipo": doc["tipo"],
                            "niveis": doc["niveis"], "trecho": i, "conteudo": texto})
    return trechos


def indexar(banco, avisar=print):
    """Recria a coleção documentos (feito uma vez, com o usuário administrador)."""
    trechos = preparar_trechos()
    emb = embeddings.obter()
    vetores = emb.codificar([f"{t['titulo']}. {t['conteudo']}" for t in trechos])
    agora = datetime.now(timezone.utc)
    for t, v in zip(trechos, vetores):
        t["embedding"] = [round(float(x), 6) for x in v]
        t["modelo_embedding"] = emb.nome
        t["indexado_em"] = agora
    banco.documentos.delete_many({})
    banco.documentos.insert_many(trechos)
    avisar(f"{len(trechos)} trechos de {len({t['arquivo'] for t in trechos})} documentos indexados "
           f"({len(vetores[0])} dimensões, modelo {emb.nome})")
    return len(trechos)


def buscar(banco, consulta, nivel, k=None):
    """Busca os k trechos mais parecidos (similaridade de cosseno), só entre os do nível certo."""
    k = k or config.RAG_TOP_K
    inicio = time.perf_counter()
    candidatos = list(banco.documentos.find({"niveis": {"$in": [nivel, "todos"]}},
                                            {"arquivo": 1, "titulo": 1, "trecho": 1, "conteudo": 1, "embedding": 1}))
    if not candidatos:
        raise RuntimeError("a coleção documentos está vazia. Rode: python cli.py indexar-documentos")
    q = embeddings.obter().codificar([consulta])[0]
    matriz = np.asarray([c["embedding"] for c in candidatos], dtype="float32")
    notas = matriz @ q
    ordem = np.argsort(-notas)[:k]
    resultado = [{"arquivo": candidatos[i]["arquivo"], "titulo": candidatos[i]["titulo"],
                  "trecho": candidatos[i]["trecho"], "conteudo": candidatos[i]["conteudo"],
                  "similaridade": round(float(notas[i]), 3)} for i in ordem]
    return resultado, round(time.perf_counter() - inicio, 3)


def consulta_para_nivel(nivel):
    """Texto de busca usado para cada nível de risco."""
    return {
        "alto": "risco alto de cheia do Rio Cachoeira: protocolo de resposta, abrigo, sair de casa, local alto, não atravessar área alagada",
        "medio": "risco médio de cheia do Rio Cachoeira: atenção, separar documentos, elevar móveis, abrigo do setor, acompanhar",
        "baixo": "risco baixo de cheia do Rio Cachoeira: situação normal, rotina, kit de emergência, acompanhar a previsão",
    }[nivel]
