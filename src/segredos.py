"""Verificação de segredos (Entrega 3): confere que nenhuma chave ou senha está nos arquivos do projeto.

Duas buscas em todos os arquivos que vão para o GitHub (tudo menos .env, .venv, .git, modelos e caches):
1. Os VALORES reais do .env (senhas, chave do Gemini, token do bot, chave de criptografia, sal, token da API).
   Se algum deles aparecer em qualquer arquivo, é vazamento.
2. Formatos conhecidos de segredo, mesmo que não sejam os nossos: chave do Google (AIza...), token de bot
   do Telegram, connection string do MongoDB com senha e campos "password"/"apiKey" preenchidos.

O fluxo do n8n exportado (n8n/*.json) recebe uma conferência a mais: as credenciais só podem aparecer
como referência (id e nome), nunca com o valor.
Gera resultados/seguranca/segredos.md e .json.
"""
import json
import re
from datetime import datetime

from . import config

IGNORAR_PASTAS = {".git", ".venv", "venv", "__pycache__", "modelos", ".pytest_cache", ".ipynb_checkpoints",
                  "node_modules"}
IGNORAR_ARQUIVOS = {".env"}
# variáveis do .env que não são segredo (nomes de modelo, datas, endereço local...)
NAO_SECRETAS = {"MONGODB_HOST", "MONGODB_BANCO", "MONGODB_ADMIN_USUARIO", "GEMINI_MODELO", "PROMPT_ALERTA_VERSAO",
                "MODO_OPERACAO", "REPRODUCAO_INICIO", "LIMIAR_TR_ALVO", "ANO_CORTE_TREINO",
                "TELEGRAM_CHAT_ALERTAS", "EMBEDDINGS_MODELO", "API_HOST", "API_PORTA", "API_URL"}
PADROES = {
    "chave do Google (AIza...)": re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    "token de bot do Telegram": re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b"),
    "connection string com senha": re.compile(r"mongodb(\+srv)?://[^:\s/\"'{]+:(?!SENHA|\.\.\.|<|\{)[^@\s\"'{]{4,}@"),
    "campo de senha preenchido": re.compile(r"\"(password|apiKey|accessToken|apiToken|secret)\"\s*:\s*\"(?!\{\{|=)"
                                            r"[^\"]{12,}\""),
}


def _ler_env():
    valores = {}
    arquivo = config.RAIZ / ".env"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                valores[k.strip()] = v.strip()
    return valores


def _arquivos():
    for caminho in sorted(config.RAIZ.rglob("*")):
        if not caminho.is_file() or caminho.name in IGNORAR_ARQUIVOS:
            continue
        partes = set(caminho.relative_to(config.RAIZ).parts)
        if partes & IGNORAR_PASTAS:
            continue
        if caminho.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf", ".zip", ".joblib", ".pkl", ".bin", ".pyc"}:
            continue
        if caminho.stat().st_size > 20_000_000:
            continue
        yield caminho


def _credenciais_n8n(caminho):
    """No fluxo exportado, cada nó só pode citar a credencial por id e nome."""
    achados = []
    try:
        fluxo = json.loads(caminho.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return [f"{caminho.name}: não é um JSON válido"]
    for no in fluxo.get("nodes", []):
        for tipo, cred in (no.get("credentials") or {}).items():
            extras = set(cred) - {"id", "name"}
            if extras:
                achados.append(f"nó '{no.get('name')}': credencial {tipo} traz campos {sorted(extras)}")
        texto = json.dumps(no.get("parameters", {}), ensure_ascii=False)
        if re.search(r"X-Token\"\s*,\s*\"value\"\s*:\s*\"[^\"={]", texto):
            achados.append(f"nó '{no.get('name')}': cabeçalho X-Token com valor escrito no nó")
    return achados


def verificar(avisar=print):
    env = _ler_env()
    segredos = {k: v for k, v in env.items() if k not in NAO_SECRETAS and len(v) >= 8}
    achados, arquivos_lidos, fluxos = [], 0, []
    for caminho in _arquivos():
        try:
            texto = caminho.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        arquivos_lidos += 1
        rel = str(caminho.relative_to(config.RAIZ)).replace("\\", "/")
        for nome, valor in segredos.items():
            if valor in texto:
                achados.append({"arquivo": rel, "tipo": f"valor real de {nome} do .env"})
        for nome, padrao in PADROES.items():
            for m in padrao.finditer(texto):
                achados.append({"arquivo": rel, "tipo": nome, "trecho": m.group(0)[:12] + "..."})
        if rel.startswith("n8n/") and rel.endswith(".json"):
            problemas = _credenciais_n8n(caminho)
            fluxos.append({"arquivo": rel, "problemas": problemas})
            achados += [{"arquivo": rel, "tipo": p} for p in problemas]

    gitignore = (config.RAIZ / ".gitignore")
    env_ignorado = gitignore.exists() and ".env" in gitignore.read_text(encoding="utf-8").split()
    resultado = {"data": datetime.now().isoformat(timespec="seconds"), "arquivos_verificados": arquivos_lidos,
                 "valores_do_env_procurados": len(segredos), "env_no_gitignore": env_ignorado,
                 "fluxos_n8n": fluxos, "achados": achados}
    pasta = config.PASTA_RESULTADOS / "seguranca"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "segredos.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Verificação de segredos ({datetime.now().strftime('%d/%m/%Y %H:%M')})", "",
          f"- Arquivos verificados: {arquivos_lidos} (tudo o que vai para o GitHub)",
          f"- Valores reais do .env procurados: {len(segredos)} (nomes das variáveis: "
          f"{', '.join(sorted(segredos)) or 'nenhum'})",
          f"- .env listado no .gitignore: {'sim' if env_ignorado else 'NÃO'}",
          f"- Fluxos do n8n conferidos: {', '.join(f['arquivo'] for f in fluxos) or 'nenhum'}",
          f"- Segredos encontrados: {len(achados)}", ""]
    if achados:
        md += ["| Arquivo | O que foi encontrado |", "|---|---|"]
        md += [f"| {a['arquivo']} | {a['tipo']} |" for a in achados]
    else:
        md.append("Nenhum segredo encontrado. As credenciais do n8n aparecem só como referência (id e nome); "
                  "os valores ficam guardados dentro do próprio n8n, no computador local.")
    (pasta / "segredos.md").write_text("\n".join(md), encoding="utf-8")
    avisar(f"{arquivos_lidos} arquivos verificados; {len(segredos)} valores do .env procurados; "
           f"segredos encontrados: {len(achados)}.")
    for a in achados:
        avisar(f"  ATENÇÃO: {a['arquivo']}: {a['tipo']}")
    return resultado
