"""Consulta ao banco pedida em linguagem natural, respeitando as permissões de quem pediu.

1. O Gemini só escolhe uma das consultas prontas (intenção). Ele não monta consulta e não vê dados.
2. A consulta roda com o usuário e a senha de quem perguntou. Se o papel dessa pessoa não pode ler
   a coleção, o MongoDB recusa, e a IA não tem como contornar isso.
3. Tudo é registrado na auditoria pelo svc_ia: quem pediu, a pergunta (anonimizada), o que a IA entendeu,
   o que ela consultou, se o banco permitiu, o que ela respondeu e quando (auditoria completa, Entrega 3).
"""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone

from pymongo.errors import OperationFailure

from .. import config
from ..db import conectar, conectar_como, eh_falta_de_permissao
from ..seguranca import anonimizar, validar_setor
from .alerta import carregar_prompt, preencher
from .llm import Gemini, LLMIndisponivel

INTENCOES = {
    "risco_atual": {"colecao": "previsoes", "filtro": {}, "ordem": ("data_hora", -1), "limite": 1,
                    "campos": {"_id": 0, "data_referencia": 1, "probabilidade": 1, "nivel_risco": 1, "variaveis": 1}},
    "ultimos_alertas": {"colecao": "alertas", "filtro": {}, "ordem": ("enviado_em", -1), "limite": 5,
                        "campos": {"_id": 0, "enviado_em": 1, "nivel_risco": 1, "texto": 1, "setores": 1}},
    # relatos e auditoria são lidos pelas views mascaradas; moradores só existe na coleção original
    "relatos_recentes": {"colecao": "vw_relatos_anonimizados", "filtro": {}, "ordem": ("recebido_em", -1),
                         "limite": 5, "campos": {"_id": 0, "recebido_em": 1, "setor": 1, "texto_anonimizado": 1,
                                                 "classe": 1}},
    # mesmo para quem pode ler moradores (svc_bot), a IA só devolve o apelido mascarado e o setor:
    # o id cifrado do Telegram nunca entra numa resposta
    "moradores_por_setor": {"colecao": "moradores", "filtro": {}, "ordem": ("inscrito_em", -1), "limite": 10,
                            "campos": {"_id": 0, "apelido_mascarado": 1, "setor": 1, "ativo": 1}},
    "auditoria_recente": {"colecao": "vw_auditoria_mascarada", "filtro": {}, "ordem": ("data_hora", -1),
                          "limite": 10, "campos": {"data_hora": 1, "usuario": 1, "acao": 1, "colecao": 1, "ip": 1}},
}
PALAVRAS = [
    ("moradores_por_setor", ["morador", "telefone", "contato", "inscrit", "cadastr"]),
    ("relatos_recentes", ["relato", "mensage", "reclama"]),
    ("auditoria_recente", ["auditoria", "acesso", "log"]),
    ("ultimos_alertas", ["alerta", "aviso"]),
    ("risco_atual", ["risco", "previs", "cheia", "rio", "vazao"]),
]


def _simples(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def intencao_por_palavras(pergunta):
    simples = _simples(pergunta)
    for intencao, palavras in PALAVRAS:
        if any(p in simples for p in palavras):
            return intencao
    return "fora_do_escopo"


def descobrir_intencao(pergunta, llm=None, usar_llm=True):
    """Usa o Gemini; se ele não estiver disponível (ou usar_llm=False), usa palavras-chave."""
    try:
        if not usar_llm:
            raise LLMIndisponivel("palavras-chave pedidas")
        llm = llm or Gemini()
        sistema, usuario = carregar_prompt("intencao", "v1")
        r = llm.gerar(sistema, preencher(usuario, {"pergunta": pergunta[:500]}), json_saida=True, max_tokens=60)
        dados = json.loads(re.search(r"\{.*\}", r["texto"], re.S).group(0))
        intencao = dados.get("intencao")
        if intencao not in INTENCOES and intencao != "fora_do_escopo":
            intencao = intencao_por_palavras(pergunta)
        setor = validar_setor(str(dados.get("setor") or ""))
        return intencao, setor, "gemini", r
    except (LLMIndisponivel, AttributeError, ValueError):
        setor = None
        m = re.search(r"setor\s*0?([1-6])", _simples(pergunta))
        if m:
            setor = validar_setor(m.group(1))
        return intencao_por_palavras(pergunta), setor, "palavras-chave", None


def _texto(valor):
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, dict):
        return ", ".join(f"{k}={_texto(v)}" for k, v in valor.items())
    if isinstance(valor, list):
        return ", ".join(_texto(v) for v in valor)
    return str(valor)


def texto_da_resposta(resposta, max_linhas=3):
    """O que a IA mostrou para quem perguntou, em uma linha (vai para a auditoria)."""
    partes = [resposta["mensagem"]]
    for linha in resposta["linhas"][:max_linhas]:
        partes.append(" | ".join(f"{k}: {v}" for k, v in linha.items()))
    if len(resposta["linhas"]) > max_linhas:
        partes.append(f"(+{len(resposta['linhas']) - max_linhas} linha(s))")
    return anonimizar(" / ".join(partes))[:600]


def consultar(usuario, senha, pergunta, llm=None, banco_do_usuario=None, usar_llm=True):
    """Roda a consulta pedida com as credenciais de quem pediu. Devolve a resposta e grava a auditoria."""
    intencao, setor, metodo, uso_llm = descobrir_intencao(pergunta, llm, usar_llm)
    resposta = {"usuario": usuario, "pergunta": pergunta, "intencao": intencao, "metodo_intencao": metodo,
                "setor": setor, "permitido": None, "linhas": [], "mensagem": ""}
    cliente = None
    try:
        if intencao == "fora_do_escopo":
            resposta["mensagem"] = ("Só consigo consultar risco atual, alertas, relatos, moradores e auditoria, "
                                    "conforme a permissão do seu perfil.")
            resposta["permitido"] = None
            return resposta
        q = INTENCOES[intencao]
        filtro = dict(q["filtro"])
        if setor and q["colecao"] in ("vw_relatos_anonimizados", "moradores"):
            filtro["setor"] = setor
        if banco_do_usuario is None:
            cliente, banco_do_usuario = conectar_como(usuario, senha)
        try:
            docs = list(banco_do_usuario[q["colecao"]].find(filtro, q["campos"]).sort(*q["ordem"]).limit(q["limite"]))
            resposta["permitido"] = True
            resposta["linhas"] = [{k: _texto(v) for k, v in d.items()} for d in docs]
            resposta["mensagem"] = f"{len(docs)} registro(s) de {q['colecao']}."
        except OperationFailure as erro:
            if not eh_falta_de_permissao(erro):
                raise
            resposta["permitido"] = False
            resposta["mensagem"] = (f"Seu perfil não tem permissão para consultar {q['colecao']}. "
                                    f"O banco recusou o pedido (código {erro.code}).")
        return resposta
    finally:
        if cliente is not None:
            cliente.close()
        colecao = INTENCOES.get(intencao, {}).get("colecao", "nenhuma")
        completo = json.dumps(resposta, ensure_ascii=False, sort_keys=True, default=str)
        conectar("ia").auditoria.insert_one({
            "data_hora": datetime.now(timezone.utc), "usuario": config.USUARIOS["ia"], "acao": "consulta_ia",
            "colecao": colecao, "solicitante": usuario, "pergunta": anonimizar(pergunta)[:300],
            "intencao": intencao, "metodo_intencao": metodo, "permitido": resposta["permitido"],
            "qtd_resultados": len(resposta["linhas"]), "ip": "127.0.0.1",
            "detalhe": resposta["mensagem"][:200],
            "resposta_ia": texto_da_resposta(resposta),
            "resposta_sha256": hashlib.sha256(completo.encode("utf-8")).hexdigest(),
            "decisao_llm": anonimizar((uso_llm or {}).get("texto", ""))[:200],
            "tokens_llm": (uso_llm or {}).get("tokens_entrada", 0) + (uso_llm or {}).get("tokens_saida", 0),
        })
