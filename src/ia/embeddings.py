"""Embeddings do RAG, calculados na própria máquina (nada sai para fora)."""
import numpy as np

from .. import config

_cache = {}


class Embeddings:
    def __init__(self, nome=None):
        self.nome = nome or config.EMBEDDINGS_MODELO
        if self.nome == "teste":
            # usado só nos testes automáticos, onde não há o modelo baixado
            from sklearn.feature_extraction.text import HashingVectorizer
            self._hv = HashingVectorizer(n_features=384, alternate_sign=False, analyzer="char_wb",
                                         ngram_range=(3, 5), norm=None)
            self._modelo = None
        else:
            from sentence_transformers import SentenceTransformer
            self._modelo = SentenceTransformer(self.nome)

    def codificar(self, textos):
        if self._modelo is None:
            matriz = self._hv.transform(textos).toarray().astype("float32")
        else:
            matriz = np.asarray(self._modelo.encode(list(textos), show_progress_bar=False), dtype="float32")
        normas = np.linalg.norm(matriz, axis=1, keepdims=True)
        return matriz / np.where(normas == 0, 1, normas)


def obter(nome=None):
    nome = nome or config.EMBEDDINGS_MODELO
    if nome not in _cache:
        _cache[nome] = Embeddings(nome)
    return _cache[nome]
