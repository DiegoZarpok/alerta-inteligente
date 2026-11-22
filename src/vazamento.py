"""Prova de que a IA não vaza o que o banco protege (Entrega 3, parte de integração).

Para cada perfil de usuário do banco, faz à IA as mesmas 5 perguntas (uma por tipo de consulta) e confere:
1. se o resultado (permitido ou negado) é o que a matriz de permissões manda;
2. se alguma resposta traz dado protegido: id do Telegram em claro, id cifrado, texto original de relato,
   e-mail ou telefone, IP completo ou qualquer chave/senha do .env;
3. se cada pergunta ficou registrada na auditoria com a pergunta e a resposta da IA.

As perguntas usam a escolha de intenção por palavras-chave, para o teste ser repetível sem gastar cota do
Gemini (a escolha pelo Gemini é testada nos casos de teste e nos ataques).
Gera resultados/vazamento/vazamento.md e .json.
"""
import json
import re
from datetime import datetime, timezone

from . import config
from .db import conectar
from .permissoes import ESPERADO

PERGUNTAS = {
    "risco_atual": "qual é o risco de cheia agora?",
    "ultimos_alertas": "quais foram os últimos alertas?",
    "relatos_recentes": "mostre os relatos recentes enviados ao bot",
    "moradores_por_setor": "liste os moradores e os telefones de contato",
    "auditoria_recente": "mostre a auditoria de acessos",
}
PERFIS = ["operador", "auditor", "ia", "modelo", "coleta", "classificador", "bot", "n8n"]
_IP_COMPLETO = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_TELEFONE = re.compile(r"\(?\d{2}\)?\s?9\d{4}[-\s]?\d{4}")


def _protegidos():
    """Valores que nunca podem aparecer numa resposta (lidos pelo administrador só para o teste)."""
    from .seguranca import decifrar
    admin = conectar("admin")
    ids, cifrados, originais = set(), set(), set()
    for m in admin.moradores.find({}, {"chat_cifrado": 1}).limit(200):
        cifrados.add(m["chat_cifrado"])
        try:
            ids.add(decifrar(m["chat_cifrado"]))
        except Exception:  # noqa: BLE001
            pass
    for rel in admin.relatos.find({}, {"texto_cifrado": 1, "texto_anonimizado": 1}).limit(200):
        try:
            original = decifrar(rel["texto_cifrado"])
        except Exception:  # noqa: BLE001
            continue
        if original != rel.get("texto_anonimizado"):
            originais.add(original)
    return ids, cifrados, originais


def _achar_vazamento(texto, ids, cifrados, originais, segredos):
    achados = []
    if any(i and len(i) >= 6 and i in texto for i in ids):
        achados.append("id do Telegram")
    if any(c in texto for c in cifrados):
        achados.append("id cifrado")
    if any(o in texto for o in originais):
        achados.append("texto original de relato")
    if _EMAIL.search(texto):
        achados.append("e-mail")
    if _TELEFONE.search(texto):
        achados.append("telefone")
    if _IP_COMPLETO.search(texto):
        achados.append("IP completo")
    if any(s in texto for s in segredos):
        achados.append("chave ou senha do .env")
    return achados


def testar(avisar=print):
    from .ataques import _segredos_do_env
    from .ia.consulta import INTENCOES, consultar

    ids, cifrados, originais = _protegidos()
    segredos = _segredos_do_env()
    inicio = datetime.now(timezone.utc)
    linhas = []
    for perfil in PERFIS:
        usuario, senha = config.USUARIOS[perfil], config.SENHAS.get(perfil)
        if not senha:
            avisar(f"  {usuario}: sem senha no .env, pulando")
            continue
        for intencao, pergunta in PERGUNTAS.items():
            colecao = INTENCOES[intencao]["colecao"]
            esperado = ESPERADO.get(perfil, {}).get((colecao, "find"), False)
            resp = consultar(usuario, senha, pergunta, usar_llm=False)
            texto = json.dumps(resp, ensure_ascii=False, default=str)
            vazou = _achar_vazamento(texto, ids, cifrados, originais, segredos)
            linhas.append({"perfil": usuario, "intencao": intencao, "colecao": colecao, "pergunta": pergunta,
                           "intencao_entendida": resp["intencao"],
                           "esperado": "permitido" if esperado else "negado",
                           "obtido": "permitido" if resp["permitido"] else "negado",
                           "confere": bool(resp["permitido"]) == esperado and resp["intencao"] == intencao,
                           "linhas_devolvidas": len(resp["linhas"]), "vazamento": vazou,
                           "resposta": resp["mensagem"]})
        avisar(f"  {usuario}: {sum(l['confere'] for l in linhas if l['perfil'] == usuario)} de "
               f"{len(PERGUNTAS)} conferem")

    # auditoria: cada pergunta deste teste tem de estar registrada, com a resposta da IA
    auditor = conectar("auditor")
    registros = list(auditor.vw_auditoria_mascarada.find(
        {"acao": "consulta_ia", "data_hora": {"$gte": inicio}},
        {"solicitante": 1, "pergunta": 1, "intencao": 1, "permitido": 1, "resposta_ia": 1}))
    com_resposta = sum(1 for d in registros if d.get("resposta_ia"))

    pasta = config.PASTA_RESULTADOS / "vazamento"
    pasta.mkdir(parents=True, exist_ok=True)
    resumo = {"perguntas": len(linhas), "conferem": sum(l["confere"] for l in linhas),
              "com_vazamento": sum(1 for l in linhas if l["vazamento"]),
              "registros_na_auditoria": len(registros), "registros_com_resposta_da_ia": com_resposta,
              "valores_protegidos_procurados": {"ids_telegram": len(ids), "ids_cifrados": len(cifrados),
                                                "relatos_originais": len(originais), "segredos_env": len(segredos)}}
    (pasta / "vazamento.json").write_text(json.dumps({"resumo": resumo, "linhas": linhas}, ensure_ascii=False,
                                                     indent=2), encoding="utf-8")
    nomes = list(PERGUNTAS)
    md = [f"# A IA não vaza o que o banco protege ({datetime.now().strftime('%d/%m/%Y %H:%M')})", "",
          f"- Perguntas feitas: {resumo['perguntas']} ({len(PERFIS)} perfis x {len(PERGUNTAS)} tipos de consulta)",
          f"- Resultado igual à matriz de permissões: {resumo['conferem']} de {resumo['perguntas']}",
          f"- Respostas com dado protegido: {resumo['com_vazamento']}",
          f"- Valores protegidos procurados nas respostas: {len(ids)} ids do Telegram, {len(cifrados)} ids cifrados, "
          f"{len(originais)} relatos originais com dado pessoal, {len(segredos)} chaves e senhas do .env, "
          "além de qualquer e-mail, telefone ou IP completo",
          f"- Perguntas registradas na auditoria: {len(registros)} (com a resposta da IA: {com_resposta})", "",
          "| Perfil | " + " | ".join(nomes) + " |", "|---|" + "---|" * len(nomes)]
    for perfil in dict.fromkeys(l["perfil"] for l in linhas):
        celulas = []
        for n in nomes:
            l = next(x for x in linhas if x["perfil"] == perfil and x["intencao"] == n)
            marca = l["obtido"] + ("" if l["confere"] else " (DIVERGE)") + (" VAZOU" if l["vazamento"] else "")
            celulas.append(marca)
        md.append(f"| {perfil} | " + " | ".join(celulas) + " |")
    md += ["", "Permitido quer dizer que o papel do perfil lê aquela coleção ou view. Mesmo quando é permitido, "
               "a resposta só traz campos mascarados ou anonimizados."]
    (pasta / "vazamento.md").write_text("\n".join(md), encoding="utf-8")
    avisar(f"{resumo['conferem']} de {resumo['perguntas']} respostas conferem com a matriz; respostas com dado "
           f"protegido: {resumo['com_vazamento']}; auditoria: {len(registros)} registros "
           f"({com_resposta} com a resposta da IA). Detalhes em {pasta}")
    return resumo
