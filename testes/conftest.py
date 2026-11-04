"""Configuração dos testes automáticos.

Precisa de um servidor compatível com MongoDB em localhost:27017 sem autenticação (nos testes do
grupo foi usado o FerretDB). As permissões, views e validações são simuladas por simulador_mongo.py.
"""
import os
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
if os.environ.get("PYMONGO_SRC"):
    sys.path.insert(0, os.environ["PYMONGO_SRC"])

os.environ.update({
    "MONGODB_SEM_AUTH": "1",
    "MONGODB_BANCO": f"teste_alerta_{secrets.token_hex(3)}",
    "ALERTA_CHAVE": secrets.token_hex(32),
    "ALERTA_SAL": "sal-de-teste-123",
    "API_TOKEN": "token-de-teste",
    "EMBEDDINGS_MODELO": "teste",
    "GEMINI_API_KEY": "chave-falsa",
    "TELEGRAM_BOT_TOKEN": "123:falso",
    "TELEGRAM_CHAT_ALERTAS": "-1001234",
    "SENHA_OPERADOR": "senha-operador",
    "SENHA_AUDITOR": "senha-auditor",
    "PROMPT_ALERTA_VERSAO": "v2",
    "MODO_OPERACAO": "reproducao",
})
for perfil in ("SVC_COLETA", "SVC_MODELO", "SVC_IA", "SVC_CLASSIFICADOR", "SVC_BOT", "SVC_N8N"):
    os.environ[f"SENHA_{perfil}"] = f"senha-{perfil.lower()}"

import pytest  # noqa: E402
