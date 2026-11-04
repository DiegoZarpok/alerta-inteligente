"""Hash, criptografia e anonimização dos dados de moradores.

O formato da criptografia é o mesmo do script banco/02_carga_inicial.js:
iv.tag.dados, cada parte em base64 (AES-256-GCM).
"""
import base64
import hashlib
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config

SETORES = [f"Setor Ribeirinho 0{i}" for i in range(1, 7)]


def _chave():
    chave = config.CHAVE_CRIPTO or ""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", chave):
        raise RuntimeError("ALERTA_CHAVE ausente ou inválida no .env (precisa de 64 caracteres hexadecimais)")
    return bytes.fromhex(chave)


def hash_morador(chat_id):
    if not config.SAL_HASH or len(config.SAL_HASH) < 8:
        raise RuntimeError("ALERTA_SAL ausente no .env (mínimo de 8 caracteres)")
    return hashlib.sha256((config.SAL_HASH + str(chat_id)).encode("utf-8")).hexdigest()


def cifrar(texto):
    iv = os.urandom(12)
    saida = AESGCM(_chave()).encrypt(iv, str(texto).encode("utf-8"), None)
    dados, tag = saida[:-16], saida[-16:]  # a biblioteca devolve dados + tag juntos
    return ".".join(base64.b64encode(p).decode() for p in (iv, tag, dados))


def decifrar(cifrado):
    iv, tag, dados = (base64.b64decode(p) for p in cifrado.split("."))
    return AESGCM(_chave()).decrypt(iv, dados + tag, None).decode("utf-8")


_NOME = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+"
_PADROES = [
    (re.compile(r"\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}"), "[TELEFONE]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"\b(Rua|Avenida|Av\.|Travessa)\s+[^,.;]+,\s*(n[ºo°]?\s*)?\d+", re.IGNORECASE), "[ENDERECO]"),
    (re.compile(r"\b([Mm]eu nome é|[Mm]e chamo|[Ss]ou o|[Ss]ou a|[Aa]qui é o|[Aa]qui é a)\s+"
                + _NOME + r"(\s+" + _NOME + r")*"), r"\1 [NOME]"),
]


def anonimizar(texto):
    for padrao, troca in _PADROES:
        texto = padrao.sub(troca, texto)
    return texto


def validar_setor(entrada):
    """Aceita só '1' a '6' ou '01' a '06'. Qualquer outra coisa (inclusive operadores
    como {"$ne": null}) é recusada, o que impede injeção NoSQL pelo bot."""
    if not isinstance(entrada, str):
        return None
    m = re.fullmatch(r"\s*(?:setor\s*(?:ribeirinho\s*)?)?0?([1-6])\s*", entrada, re.IGNORECASE)
    return f"Setor Ribeirinho 0{m.group(1)}" if m else None
