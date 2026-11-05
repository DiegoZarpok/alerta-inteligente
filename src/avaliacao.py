"""Comparação das versões do prompt e medição de custo e tempo de resposta."""
import json
import statistics
import time
from datetime import datetime

from . import config
from .db import conectar
from .ia import alerta
from .ia.llm import PRECOS, Gemini, LLMIndisponivel

# Cenários fixos (mesmos para as duas versões): nível, probabilidade e vazão como o modelo entregaria
CENARIOS = [
    ("medio", 0.34, 412), ("medio", 0.41, 520), ("medio", 0.47, 610), ("medio", 0.52, 733), ("medio", 0.58, 801),
    ("alto", 0.63, 690), ("alto", 0.71, 845), ("alto", 0.78, 902), ("alto", 0.86, 1110), ("alto", 0.93, 1385),
]


def _previsao(nivel, p, q):
    return {"previsao_id": "cenario", "nivel_risco": nivel, "probabilidade": p, "vazao_m3s": q,
            "limiar_m3s": 930.0, "data_referencia": ""}


def _estatisticas(valores):
    valores = [v for v in valores if v is not None]
    if not valores:
        return None
    ordenados = sorted(valores)
    p95 = ordenados[min(len(ordenados) - 1, int(round(0.95 * (len(ordenados) - 1))))]
    return {"media": round(statistics.mean(valores), 3), "mediana": round(statistics.median(valores), 3),
            "p95": round(p95, 3), "min": round(min(valores), 3), "max": round(max(valores), 3)}


def avaliar_prompts(versoes=("v1", "v2"), pausa=4.0):
    banco = conectar("ia")
    llm = Gemini()
    linhas = []
    for versao in versoes:
        for nivel, p, q in CENARIOS:
            r = alerta.escrever(_previsao(nivel, p, q), banco, "alerta", versao, llm)
            linhas.append({"versao": versao, "nivel": nivel, "probabilidade": p, "vazao": q,
                           "aprovado": r["validado"], "problemas": r["problemas"],
                           "caracteres": len(r["texto_gerado"] or ""), "tokens_entrada": r["tokens_entrada"],
                           "tokens_saida": r["tokens_saida"], "latencia_llm_s": r["latencia_llm_s"],
                           "texto_gerado": r["texto_gerado"]})
            print(f"  {versao} {nivel} {p:.2f}: {'aprovado' if r['validado'] else 'bloqueado ' + str(r['problemas'])}")
            time.sleep(pausa)  # respeita o limite de pedidos por minuto do nível gratuito
    resumo = {}
    for versao in versoes:
        sub = [l for l in linhas if l["versao"] == versao]
        problemas = {}
        for l in sub:
            for pr in l["problemas"]:
                chave = pr.split("(")[0].split(":")[0].strip()
                problemas[chave] = problemas.get(chave, 0) + 1
        resumo[versao] = {"aprovados": sum(l["aprovado"] for l in sub), "total": len(sub),
                          "caracteres_media": round(statistics.mean(l["caracteres"] for l in sub)),
                          "tokens_entrada_media": round(statistics.mean(l["tokens_entrada"] for l in sub)),
                          "tokens_saida_media": round(statistics.mean(l["tokens_saida"] for l in sub)),
                          "problemas_mais_comuns": problemas}
    pasta = config.PASTA_RESULTADOS / "prompts"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "comparacao.json").write_text(json.dumps({"modelo": llm.modelo, "resumo": resumo, "linhas": linhas},
                                                      ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Comparação dos prompts do alerta ({datetime.now().strftime('%d/%m/%Y %H:%M')})", "",
          f"Modelo: {llm.modelo}. Os mesmos {len(CENARIOS)} cenários foram enviados às duas versões.", "",
          "| Versão | Aprovados pelo validador | Caracteres (média) | Tokens de entrada | Tokens de saída |",
          "|---|---|---|---|---|"]
    for v, r in resumo.items():
        md.append(f"| {v} | {r['aprovados']}/{r['total']} | {r['caracteres_media']} | {r['tokens_entrada_media']} | "
                  f"{r['tokens_saida_media']} |")
    md += ["", "Problemas encontrados pelo validador:"]
    for v, r in resumo.items():
        md.append(f"- {v}: " + (", ".join(f"{k} ({n})" for k, n in r["problemas_mais_comuns"].items()) or "nenhum"))
    md += ["", "Exemplo de texto de cada versão (cenário de risco alto, 71%):"]
    for v in versoes:
        ex = next((l for l in linhas if l["versao"] == v and l["probabilidade"] == 0.71), None)
        if ex:
            md.append(f"- {v}: {ex['texto_gerado']}")
    (pasta / "comparacao.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Resultado salvo em {pasta}")
    return resumo


def medir_custo_latencia(repeticoes=20, modelos=None, pausa=4.0):
    """Mede tempo e custo por alerta. Chamadas em que o Gemini falhou (e o sistema usou o texto padrão)
    são contadas à parte e não entram na média de tokens e custo."""
    banco = conectar("ia")
    modelos = modelos or [config.GEMINI_MODELO]
    resultado = {}
    for nome in modelos:
        try:
            llm = Gemini(modelo=nome)
        except LLMIndisponivel as erro:
            print(f"  {nome}: {erro}")
            continue
        medidas, falhas = [], []
        for i in range(repeticoes):
            nivel, p, q = CENARIOS[i % len(CENARIOS)]
            inicio = time.perf_counter()
            r = alerta.escrever(_previsao(nivel, p, q), banco, "alerta", config.PROMPT_ALERTA_VERSAO, llm)
            total = time.perf_counter() - inicio
            if r["modelo_llm"] is None:  # o Gemini não respondeu: o sistema usou o texto padrão
                motivo = (r["problemas"] or ["sem detalhe"])[0]
                falhas.append({"total_s": round(total, 2), "motivo": motivo[:300]})
                print(f"  {nome} {i + 1}/{repeticoes}: {total:.2f} s, FALHOU (texto padrão usado): {motivo[:120]}")
            else:
                tentativas = r.get("tentativas_llm") or [200]
                medidas.append({"total_s": total, "llm_s": r["latencia_llm_s"], "busca_s": r["latencia_busca_s"],
                                "entrada": r["tokens_entrada"], "saida": r["tokens_saida"],
                                "raciocinio": r["tokens_raciocinio"], "custo": r["custo_usd"] or 0.0,
                                "aprovado": r["validado"], "tentativas": tentativas})
                extra = "" if len(tentativas) == 1 else f" (tentativas: {tentativas})"
                print(f"  {nome} {i + 1}/{repeticoes}: {total:.2f} s, {r['tokens_entrada']}+{r['tokens_saida']} tokens{extra}")
            time.sleep(pausa)
        resumo = {"repeticoes": repeticoes, "respostas_do_gemini": len(medidas), "falhas": len(falhas),
                  "motivos_das_falhas": sorted({f["motivo"][:120] for f in falhas}),
                  "preco_por_milhao_usd": {"entrada": PRECOS.get(nome, (None, None))[0],
                                           "saida": PRECOS.get(nome, (None, None))[1]}}
        if medidas:
            custo_medio = statistics.mean(m["custo"] for m in medidas)
            primeira = [m["total_s"] for m in medidas if len(m["tentativas"]) == 1]
            resumo.update({
                "latencia_total_s": _estatisticas([m["total_s"] for m in medidas]),
                "latencia_total_sem_nova_tentativa_s": _estatisticas(primeira),
                "chamadas_com_nova_tentativa": sum(len(m["tentativas"]) > 1 for m in medidas),
                "latencia_llm_s": _estatisticas([m["llm_s"] for m in medidas]),
                "latencia_busca_rag_s": _estatisticas([m["busca_s"] for m in medidas]),
                "tokens_entrada_media": round(statistics.mean(m["entrada"] for m in medidas)),
                "tokens_saida_media": round(statistics.mean(m["saida"] for m in medidas)),
                "tokens_raciocinio_media": round(statistics.mean(m["raciocinio"] for m in medidas)),
                "custo_por_uso_usd": round(custo_medio, 6),
                "custo_por_1000_usos_usd": round(custo_medio * 1000, 3),
                "aprovados_validador": f"{sum(m['aprovado'] for m in medidas)}/{len(medidas)}",
            })
        if falhas:
            resumo["latencia_ate_desistir_s"] = _estatisticas([f["total_s"] for f in falhas])
        resultado[nome] = resumo

    # tempo do modelo de previsão (sem o Gemini), para comparação
    from .modelo.treinar import carregar_modelo
    from .modelo.dados import VARIAVEIS
    import pandas as pd
    pacote = carregar_modelo()
    linha = pd.DataFrame([[0.5] * len(VARIAVEIS)], columns=VARIAVEIS)
    tempos = []
    for _ in range(200):
        t = time.perf_counter()
        pacote["modelo"].predict_proba(linha)
        tempos.append(time.perf_counter() - t)
    resultado["modelo_previsao"] = {"nome": pacote["nome"], "latencia_s": _estatisticas(tempos)}

    pasta = config.PASTA_RESULTADOS / "custo_latencia"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "custo_latencia.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Custo e tempo de resposta ({datetime.now().strftime('%d/%m/%Y %H:%M')})", ""]
    for nome, r in resultado.items():
        if nome == "modelo_previsao":
            md.append(f"Modelo de previsão ({r['nome']}): {r['latencia_s']['mediana'] * 1000:.1f} ms por previsão (mediana).")
            continue
        md += [f"## {nome}", f"- Chamadas: {r['repeticoes']} ({r['respostas_do_gemini']} respondidas pelo Gemini, "
               f"{r['falhas']} com falha e texto padrão)"]
        if r["respostas_do_gemini"]:
            sem = r["latencia_total_sem_nova_tentativa_s"]
            md += [f"- Tempo total por alerta: mediana {r['latencia_total_s']['mediana']} s, p95 {r['latencia_total_s']['p95']} s",
                   f"- Chamadas que precisaram de nova tentativa (limite do nível gratuito ou servidor ocupado): "
                   f"{r['chamadas_com_nova_tentativa']}"
                   + (f"; sem nova tentativa, mediana {sem['mediana']} s" if sem else ""),
                   f"- Busca no RAG: mediana {r['latencia_busca_rag_s']['mediana']} s",
                   f"- Tokens por uso: {r['tokens_entrada_media']} de entrada, {r['tokens_saida_media']} de saída, "
                   f"{r['tokens_raciocinio_media']} de raciocínio",
                   f"- Custo: US$ {r['custo_por_uso_usd']} por uso, US$ {r['custo_por_1000_usos_usd']} a cada 1.000 usos "
                   f"(preço do nível pago)",
                   f"- Textos aprovados pelo validador: {r['aprovados_validador']}"]
        if r["falhas"]:
            md.append(f"- Motivos das falhas: {'; '.join(r['motivos_das_falhas'])}")
        md.append("")
    (pasta / "custo_latencia.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Resultado salvo em {pasta}")
    return resultado
