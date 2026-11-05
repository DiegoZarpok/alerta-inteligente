"""Geração do alerta (e da resposta ao /risco): RAG + Gemini + validador, com registro e auditoria.

Quem decide o nível de risco é o modelo matemático. Aqui o Gemini só escreve o texto.
O Gemini recebe apenas números públicos e trechos dos documentos; nenhum dado de morador.
"""
import re
import time
from datetime import datetime, timezone

from bson import ObjectId

from .. import config
from ..seguranca import SETORES
from . import rag
from .llm import Gemini, LLMIndisponivel
from .validador import validar

SETORES_POR_NIVEL = {"baixo": [], "medio": SETORES[:3], "alto": SETORES[:5]}
ABRIGO_DO_SETOR = {SETORES[0]: "Abrigo A", SETORES[1]: "Abrigo A", SETORES[2]: "Abrigo B",
                   SETORES[3]: "Abrigo B", SETORES[4]: "Abrigo C", SETORES[5]: "Abrigo C"}
NOME_NIVEL = {"baixo": "BAIXO", "medio": "MÉDIO", "alto": "ALTO"}


def carregar_prompt(nome, versao):
    texto = (config.PASTA_PROMPTS / f"{nome}_{versao}.md").read_text(encoding="utf-8")
    sistema = re.search(r"## Sistema\n(.*?)\n## Usuario", texto, re.S).group(1).strip()
    usuario = re.search(r"## Usuario\n(.*)$", texto, re.S).group(1).strip()
    return sistema, usuario


def preencher(modelo, valores):
    for chave, valor in valores.items():
        modelo = modelo.replace("{" + chave + "}", str(valor))
    return modelo


def _dados_do_texto(previsao):
    return {
        "nivel": previsao["nivel_risco"],
        "probabilidade_pct": int(round(previsao["probabilidade"] * 100)),
        "vazao_m3s": int(round(previsao["vazao_m3s"])),
        "limiar_m3s": previsao.get("limiar_m3s"),
        "abrigos": ["A", "B", "C"],
    }


def _valores(previsao, setores, trechos):
    d = _dados_do_texto(previsao)
    contexto = "\n\n".join(f"[{t['titulo']}]\n{t['conteudo']}" for t in trechos)
    lista_setores = ", ".join(f"{s} ({ABRIGO_DO_SETOR[s]})" for s in setores) or "nenhum"
    return {"nivel": NOME_NIVEL[d["nivel"]].lower(), "NIVEL_MAIUSCULO": NOME_NIVEL[d["nivel"]],
            "probabilidade_pct": d["probabilidade_pct"], "vazao_m3s": f"{d['vazao_m3s']}",
            "setores": lista_setores, "contexto": contexto, "data_referencia": previsao.get("data_referencia", "")}


def texto_padrao(previsao, setores):
    """Mensagem fixa do documento 24, usada quando o Gemini falha ou o validador bloqueia."""
    d = _dados_do_texto(previsao)
    abrigos = ", ".join(sorted({ABRIGO_DO_SETOR[s] for s in setores})) or "o abrigo do seu setor"
    if d["nivel"] == "alto":
        return (f"RISCO ALTO - Rio Cachoeira. Cheia provável: {d['probabilidade_pct']}%. Vazão atual: "
                f"{d['vazao_m3s']} m³/s, subindo. Procure local alto ou o {abrigos}. Não atravesse áreas "
                f"alagadas. Defesa Civil: 199")
    if d["nivel"] == "medio":
        return (f"RISCO MÉDIO - Rio Cachoeira. Probabilidade de cheia nas próximas 24 h: {d['probabilidade_pct']}%. "
                f"Vazão atual: {d['vazao_m3s']} m³/s. Separe documentos e eleve objetos. Abrigo do seu setor: "
                f"{abrigos}. Defesa Civil: 199")
    return (f"Risco BAIXO - Rio Cachoeira. Probabilidade de cheia nas próximas 24 h: {d['probabilidade_pct']}%. "
            f"Vazão atual: {d['vazao_m3s']} m³/s. Situação normal; mantenha o kit de emergência em local alto.")


def escrever(previsao, banco, nome_prompt="alerta", versao=None, llm=None):
    """Busca no RAG, chama o Gemini e valida. Devolve o texto final e as medições."""
    versao = versao or (config.PROMPT_ALERTA_VERSAO if nome_prompt == "alerta" else "v1")
    nivel = previsao["nivel_risco"]
    setores = SETORES_POR_NIVEL[nivel]
    trechos, t_busca = rag.buscar(banco, rag.consulta_para_nivel(nivel), nivel)
    sistema, usuario = carregar_prompt(nome_prompt, versao)
    valores = _valores(previsao, setores, trechos)
    sistema, usuario = preencher(sistema, valores), preencher(usuario, valores)

    medicao = {"versao_prompt": f"{nome_prompt}_{versao}", "latencia_busca_s": t_busca,
               "trechos_usados": [f"{t['arquivo']}#{t['trecho']}" for t in trechos],
               "modelo_llm": None, "tokens_entrada": 0, "tokens_saida": 0, "tokens_raciocinio": 0,
               "custo_usd": 0.0, "latencia_llm_s": None, "texto_gerado": None, "problemas": [],
               "tentativas_llm": []}
    texto, origem = None, "gemini"
    try:
        llm = llm or Gemini()
        r = llm.gerar(sistema, usuario)
        medicao.update({k: r[k] for k in ("modelo", "tokens_entrada", "tokens_saida", "tokens_raciocinio",
                                          "custo_usd")})
        medicao["modelo_llm"] = r["modelo"]
        medicao["latencia_llm_s"] = r["latencia_s"]
        medicao["tentativas_llm"] = r.get("tentativas", [])
        medicao["texto_gerado"] = r["texto"]
        ok, problemas = validar(r["texto"], _dados_do_texto(previsao))
        medicao["problemas"] = problemas
        if ok:
            texto = r["texto"]
        else:
            origem = "texto_padrao (validador bloqueou)"
    except LLMIndisponivel as erro:
        origem = "texto_padrao (Gemini indisponível)"
        medicao["problemas"] = [str(erro)]
    if texto is None:
        texto = texto_padrao(previsao, setores)
    medicao.pop("modelo", None)
    return {"texto": texto, "origem_texto": origem, "validado": origem == "gemini", "setores": setores,
            **medicao}


def previsao_do_banco(banco, previsao_id=None):
    filtro = {"_id": ObjectId(previsao_id)} if previsao_id else {}
    doc = banco.previsoes.find_one(filtro, sort=[("data_hora", -1)])
    if not doc:
        raise LookupError("nenhuma previsão encontrada")
    return {"previsao_id": str(doc["_id"]), "nivel_risco": doc["nivel_risco"], "probabilidade": doc["probabilidade"],
            "vazao_m3s": doc.get("variaveis", {}).get("vazao_m3s", 0), "limiar_m3s": doc.get("limiar_m3s"),
            "data_referencia": doc["data_referencia"].date().isoformat() if doc.get("data_referencia") else ""}


def _auditar(banco, acao, colecoes, solicitante, detalhe, extra=None):
    banco.auditoria.insert_one({"data_hora": datetime.now(timezone.utc), "usuario": config.USUARIOS["ia"],
                                "acao": acao, "colecao": colecoes, "solicitante": solicitante,
                                "ip": "127.0.0.1", "detalhe": detalhe, **(extra or {})})


def gerar_alerta(previsao_id=None, solicitante="n8n", llm=None, versao=None):
    """Usado pelo n8n. Lê a previsão (svc_ia), escreve o texto e grava o alerta."""
    from ..db import conectar
    banco = conectar("ia")
    inicio = time.perf_counter()
    previsao = previsao_do_banco(banco, previsao_id)
    if previsao["nivel_risco"] == "baixo":
        return {"enviar": False, "nivel_risco": "baixo", "previsao_id": previsao["previsao_id"]}
    r = escrever(previsao, banco, "alerta", versao, llm)
    total = round(time.perf_counter() - inicio, 3)
    doc = {"enviado_em": datetime.now(timezone.utc), "nivel_risco": previsao["nivel_risco"],
           "probabilidade": float(previsao["probabilidade"]), "texto": r["texto"], "setores": r["setores"],
           "modelo_llm": r["modelo_llm"] or "nenhum", "validado": r["validado"],
           "previsao_id": previsao["previsao_id"], "origem_texto": r["origem_texto"],
           "versao_prompt": r["versao_prompt"], "tokens_entrada": r["tokens_entrada"],
           "tokens_saida": r["tokens_saida"], "tokens_raciocinio": r["tokens_raciocinio"],
           "custo_usd": r["custo_usd"] or 0.0, "latencia_llm_s": r["latencia_llm_s"],
           "latencia_busca_s": r["latencia_busca_s"], "latencia_total_s": total,
           "trechos_usados": r["trechos_usados"], "problemas_validador": r["problemas"]}
    alerta_id = str(banco.alertas.insert_one(doc).inserted_id)
    _auditar(banco, "gerar_alerta", "previsoes, documentos, alertas", solicitante,
             f"alerta {alerta_id} da previsão {previsao['previsao_id']}; trechos {', '.join(r['trechos_usados'])}",
             {"permitido": True})
    return {"enviar": True, "alerta_id": alerta_id, "chat_id": config.TELEGRAM_CHAT_ALERTAS, **r,
            "nivel_risco": previsao["nivel_risco"], "latencia_total_s": total}


def responder_risco(solicitante, llm=None):
    """Usado pelo bot no comando /risco."""
    from ..db import conectar
    banco = conectar("ia")
    previsao = previsao_do_banco(banco)
    r = escrever(previsao, banco, "risco", "v1", llm)
    _auditar(banco, "responder_risco", "previsoes, documentos", solicitante,
             f"previsão {previsao['previsao_id']}; origem do texto: {r['origem_texto']}", {"permitido": True})
    return r["texto"]
