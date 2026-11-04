"""Teste de permissões: entra com cada usuário e tenta cada operação, comparando com o esperado.

Gera resultados/permissoes/permissoes.md e .json (evidência de acesso permitido e negado).
Os documentos de teste levam o campo teste_permissao=true e são apagados no fim pelo administrador
(menos os da auditoria, que ninguém pode apagar e ficam como registro do teste).
"""
import json
import secrets
from datetime import datetime, timezone

from pymongo.errors import OperationFailure

from . import config
from .db import conectar, conectar_como, eh_falta_de_permissao

P = True
N = False
# esperado[papel][(coleção, operação)] = permitido?  Tudo que não está listado é esperado como negado.
ESPERADO = {
    "coleta": {("series_hidrologicas", "find"): P, ("series_hidrologicas", "insert"): P, ("estacoes", "find"): P,
               ("auditoria", "insert"): P},
    "modelo": {("series_hidrologicas", "find"): P, ("estacoes", "find"): P, ("previsoes", "find"): P,
               ("previsoes", "insert"): P, ("auditoria", "insert"): P},
    "ia": {("documentos", "find"): P, ("previsoes", "find"): P, ("alertas", "insert"): P, ("auditoria", "insert"): P},
    "classificador": {("vw_relatos_anonimizados", "find"): P, ("relatos", "update"): P, ("auditoria", "insert"): P},
    "bot": {("moradores", "find"): P, ("moradores", "insert"): P, ("moradores", "update"): P,
            ("moradores", "remove"): P, ("relatos", "insert"): P, ("relatos", "remove"): P, ("alertas", "find"): P,
            ("auditoria", "insert"): P},
    "n8n": {("auditoria", "insert"): P},
    "operador": {("series_hidrologicas", "find"): P, ("estacoes", "find"): P, ("previsoes", "find"): P,
                 ("alertas", "find"): P, ("vw_moradores_mascarado", "find"): P, ("vw_relatos_anonimizados", "find"): P},
    "auditor": {("vw_auditoria_mascarada", "find"): P, ("alertas", "find"): P},
}
# pontos em que a Entrega 1 previu um DENY (negação proposital)
DENY = {("ia", "moradores", "find"), ("ia", "relatos", "find"), ("operador", "moradores", "find"),
        ("operador", "relatos", "find"), ("auditor", "auditoria", "remove"), ("ia", "auditoria", "remove"),
        ("operador", "auditoria", "remove"), ("ia", "admin", "grantRolesToUser"),
        ("operador", "admin", "grantRolesToUser")}

COLECOES = ["series_hidrologicas", "estacoes", "previsoes", "alertas", "documentos", "moradores", "relatos",
            "auditoria"]
VIEWS = ["vw_moradores_mascarado", "vw_relatos_anonimizados", "vw_auditoria_mascarada"]


def _doc_teste(colecao, usuario):
    agora = datetime.now(timezone.utc)
    base = {
        "series_hidrologicas": {"estacao_id": "TESTE", "data_hora": agora, "fonte": "TESTE", "vazao_m3s": None,
                                "chuva_mm": None, "cota_cm": None},
        "estacoes": {"_id": f"TESTE-{secrets.token_hex(3)}", "nome": "teste", "tipo": "fluviometrica"},
        "previsoes": {"data_hora": agora, "probabilidade": 0.0, "nivel_risco": "baixo", "versao_modelo": "teste"},
        "alertas": {"enviado_em": agora, "nivel_risco": "medio", "texto": "teste de permissão", "setores": []},
        "documentos": {"arquivo": "teste.md", "titulo": "teste", "conteudo": "teste", "tipo": "Próprio",
                       "trecho": secrets.randbelow(10**6) + 1000, "niveis": ["todos"], "embedding": None},
        "moradores": {"chat_hash": secrets.token_hex(32), "chat_cifrado": "teste", "setor": "Setor Ribeirinho 01",
                      "inscrito_em": agora, "ativo": False},
        "relatos": {"morador_hash": secrets.token_hex(32), "recebido_em": agora, "texto_anonimizado": "teste",
                    "texto_cifrado": "teste", "setor": "Setor Ribeirinho 01", "classe": None},
        "auditoria": {"data_hora": agora, "usuario": usuario, "acao": "teste_permissao", "colecao": "auditoria",
                      "ip": "127.0.0.1", "detalhe": "documento criado pelo teste automático de permissões"},
    }[colecao]
    base["teste_permissao"] = True
    return base


def _tentar(funcao):
    try:
        funcao()
        return True, ""
    except OperationFailure as erro:
        if eh_falta_de_permissao(erro):
            return False, f"negado pelo MongoDB (código {erro.code})"
        if erro.code == 121:  # passou da permissão, mas o validador recusou o documento
            return True, "permitido (validação de esquema recusou o documento de teste)"
        return None, f"erro {erro.code}: {erro.details.get('errmsg', '') if erro.details else erro}"


def testar(avisar=print):
    linhas = []
    for perfil in ESPERADO:
        usuario = config.USUARIOS[perfil]
        senha = config.SENHAS.get(perfil)
        if not senha:
            avisar(f"  {usuario}: sem senha no .env, pulando")
            continue
        cliente, banco = conectar_como(usuario, senha)
        operacoes = []
        for c in COLECOES:
            col = banco[c]
            operacoes += [
                (c, "find", lambda col=col: list(col.find({}).limit(1))),
                (c, "insert", lambda col=col, c=c: col.insert_one(_doc_teste(c, usuario))),
                (c, "update", lambda col=col: col.update_one({"teste_permissao": True, "_id": "inexistente"},
                                                             {"$set": {"teste_ok": True}})),
                (c, "remove", lambda col=col: col.delete_one({"teste_permissao": True, "_id": "inexistente"})),
            ]
        for v in VIEWS:
            operacoes.append((v, "find", lambda v=v: list(banco[v].find({}).limit(1))))
        operacoes.append(("admin", "grantRolesToUser", lambda: banco.command(
            "grantRolesToUser", usuario, roles=[{"role": "dbOwner", "db": config.BANCO}])))
        operacoes.append(("admin", "createUser", lambda: banco.command(
            "createUser", f"intruso_{secrets.token_hex(3)}", pwd=secrets.token_hex(12), roles=[])))

        for alvo, op, funcao in operacoes:
            esperado = ESPERADO[perfil].get((alvo, op), False)
            obtido, obs = _tentar(funcao)
            linhas.append({"usuario": usuario, "papel": f"papel_{perfil}", "alvo": alvo, "operacao": op,
                           "esperado": "permitido" if esperado else "negado",
                           "obtido": {True: "permitido", False: "negado", None: "erro"}[obtido],
                           "confere": obtido == esperado, "deny_previsto": (perfil, alvo, op) in DENY,
                           "observacao": obs})
        cliente.close()

    admin = conectar("admin")
    for c in COLECOES:
        if c != "auditoria":
            admin[c].delete_many({"teste_permissao": True})

    pasta = config.PASTA_RESULTADOS / "permissoes"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "permissoes.json").write_text(json.dumps(linhas, ensure_ascii=False, indent=2), encoding="utf-8")
    total, certos = len(linhas), sum(l["confere"] for l in linhas)
    md = [f"# Teste de permissões ({datetime.now().strftime('%d/%m/%Y %H:%M')})", "",
          f"{certos} de {total} operações tiveram o resultado esperado.", "",
          "| Usuário | Alvo | Operação | Esperado | Obtido | Confere | DENY previsto |",
          "|---|---|---|---|---|---|---|"]
    for l in linhas:
        if l["esperado"] == "permitido" or l["deny_previsto"] or not l["confere"]:
            md.append(f"| {l['usuario']} | {l['alvo']} | {l['operacao']} | {l['esperado']} | {l['obtido']} | "
                      f"{'sim' if l['confere'] else 'NÃO'} | {'sim' if l['deny_previsto'] else ''} |")
    md += ["", "A tabela mostra todas as permissões concedidas, os DENY previstos na Entrega 1 e qualquer "
               "divergência. A lista completa, com as demais negações, está em permissoes.json."]
    (pasta / "permissoes.md").write_text("\n".join(md), encoding="utf-8")
    avisar(f"{certos} de {total} operações conferem com o esperado. Detalhes em {pasta}")
    for l in linhas:
        if not l["confere"]:
            avisar(f"  DIVERGÊNCIA: {l['usuario']} {l['operacao']} em {l['alvo']}: esperado {l['esperado']}, "
                   f"obtido {l['obtido']} {l['observacao']}")
    return linhas
