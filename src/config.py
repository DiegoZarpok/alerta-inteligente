"""Configurações do projeto, lidas do arquivo .env (que nunca vai para o GitHub)."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
except ImportError:  # sem python-dotenv, vale só o que estiver no ambiente
    pass


def env(nome, padrao=None):
    valor = os.environ.get(nome)
    return padrao if valor in (None, "") else valor


def env_int(nome, padrao):
    return int(env(nome, padrao))


def env_float(nome, padrao):
    return float(env(nome, padrao))


# Pastas
PASTA_DADOS = RAIZ / "dados"
PASTA_BRUTOS = PASTA_DADOS / "brutos"
PASTA_PROCESSADOS = PASTA_DADOS / "processados"
PASTA_DOCUMENTOS = PASTA_DADOS / "documentos_rag"
PASTA_RELATOS = PASTA_DADOS / "finetuning"
PASTA_PROMPTS = RAIZ / "prompts"
PASTA_RESULTADOS = RAIZ / "resultados"
PASTA_MODELOS = RAIZ / "modelos"

# MongoDB
MONGO_HOST = env("MONGODB_HOST", "localhost:27017")
BANCO = env("MONGODB_BANCO", "alerta_inteligente")
MONGO_SEM_AUTH = env("MONGODB_SEM_AUTH", "0") == "1"  # só para testes locais

# Cada serviço entra no banco com o próprio usuário (privilégio mínimo)
USUARIOS = {
    "admin": env("MONGODB_ADMIN_USUARIO", "admin"),
    "coleta": "svc_coleta",
    "modelo": "svc_modelo",
    "ia": "svc_ia",
    "classificador": "svc_classificador",
    "bot": "svc_bot",
    "n8n": "svc_n8n",
    "operador": "operador_defesa_civil",
    "auditor": "auditor",
}
SENHAS = {
    "admin": env("MONGODB_ADMIN_SENHA"),
    "coleta": env("SENHA_SVC_COLETA"),
    "modelo": env("SENHA_SVC_MODELO"),
    "ia": env("SENHA_SVC_IA"),
    "classificador": env("SENHA_SVC_CLASSIFICADOR"),
    "bot": env("SENHA_SVC_BOT"),
    "n8n": env("SENHA_SVC_N8N"),
    "operador": env("SENHA_OPERADOR"),
    "auditor": env("SENHA_AUDITOR"),
}

# Proteção de dados dos moradores
CHAVE_CRIPTO = env("ALERTA_CHAVE")
SAL_HASH = env("ALERTA_SAL")

# Estudo da UESC (Farias e Gomes, 2023): estação Contorno da BR-101 e tempo de retorno do alvo
ESTACAO_ALVO = env("ESTACAO_ALVO", "53180000")
TR_ALVO = env_float("LIMIAR_TR_ALVO", 3)
ANO_CORTE_TREINO = env_int("ANO_CORTE_TREINO", 2000)
CORTE_MEDIO = env_float("CORTE_RISCO_MEDIO", 0.30)
CORTE_ALTO = env_float("CORTE_RISCO_ALTO", 0.60)

# Gemini
GEMINI_CHAVE = env("GEMINI_API_KEY")
GEMINI_MODELO = env("GEMINI_MODELO", "gemini-3.5-flash-lite")
GEMINI_URL_BASE = env("GEMINI_URL_BASE", "https://generativelanguage.googleapis.com")
PROMPT_ALERTA_VERSAO = env("PROMPT_ALERTA_VERSAO", "v2")

# Embeddings do RAG ("teste" usa um vetorizador simples, só para os testes automáticos)
EMBEDDINGS_MODELO = env("EMBEDDINGS_MODELO", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
RAG_TOP_K = env_int("RAG_TOP_K", 4)

# Telegram
TELEGRAM_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ALERTAS = env("TELEGRAM_CHAT_ALERTAS")
TELEGRAM_URL_BASE = env("TELEGRAM_URL_BASE", "https://api.telegram.org")

# API local chamada pelo n8n e pelo bot
API_HOST = env("API_HOST", "127.0.0.1")
API_PORTA = env_int("API_PORTA", 8000)
API_TOKEN = env("API_TOKEN")
API_URL = env("API_URL", f"http://127.0.0.1:{API_PORTA}")

# Operação: "reproducao" roda um dia histórico como se fosse hoje; "tempo_real" usa a telemetria da ANA
MODO_OPERACAO = env("MODO_OPERACAO", "reproducao")
REPRODUCAO_INICIO = env("REPRODUCAO_INICIO", "2007-12-01")
INTERVALO_MIN_BAIXO = env_int("INTERVALO_MIN_BAIXO", 55)
