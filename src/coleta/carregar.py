"""Grava as séries da ANA no MongoDB com o usuário svc_coleta (só consulta e insere)."""
from collections import defaultdict
from datetime import date, datetime, timezone

from .. import config
from ..db import conectar
from .ana import ESTACOES, baixar_telemetria, ler_bruto


def _documento(codigo, tipo, dia, valor, fonte, extra=None):
    doc = {"estacao_id": codigo, "data_hora": datetime.combine(dia, datetime.min.time()),
           "cota_cm": None, "vazao_m3s": None, "chuva_mm": None, "fonte": fonte}
    if valor is not None and valor < 0:  # leitura inválida
        valor = None
    doc["vazao_m3s" if tipo == "vazao" else "chuva_mm"] = None if valor is None else float(valor)
    doc.update(extra or {})
    return doc


def carregar_series(avisar=print):
    banco = conectar("coleta")
    total = 0
    for codigo, info in ESTACOES.items():
        linhas = ler_bruto(codigo, info["tipo"])
        if not linhas:
            avisar(f"  {codigo} {info['nome']}: sem arquivo em dados/brutos, pulando")
            continue
        existentes = set(banco.series_hidrologicas.distinct("data_hora", {"estacao_id": codigo, "fonte": "ANA"}))
        novos = [_documento(codigo, info["tipo"], d, v, "ANA", {"nivel_consistencia": n})
                 for d, v, n in linhas if datetime.combine(d, datetime.min.time()) not in existentes]
        for i in range(0, len(novos), 5000):
            banco.series_hidrologicas.insert_many(novos[i:i + 5000], ordered=False)
        total += len(novos)
        avisar(f"  {codigo} {info['nome']}: {len(novos)} dias novos ({len(existentes)} já estavam no banco)")
    banco.auditoria.insert_one({"data_hora": datetime.now(timezone.utc), "usuario": config.USUARIOS["coleta"],
                                "acao": "insert", "colecao": "series_hidrologicas", "ip": "127.0.0.1",
                                "detalhe": f"carga das séries da ANA: {total} documentos"})
    return total


def coletar_tempo_real(avisar=print):
    """Lê a telemetria da ANA dos últimos dias e grava a média (vazão) ou a soma (chuva) de cada dia."""
    banco = conectar("coleta")
    gravados = 0
    for codigo, info in ESTACOES.items():
        try:
            leituras = baixar_telemetria(codigo)
        except Exception as erro:  # estação sem telemetria ou serviço fora do ar
            avisar(f"  {codigo}: telemetria indisponível ({erro})")
            continue
        por_dia = defaultdict(list)
        for l in leituras:
            v = l["vazao"] if info["tipo"] == "vazao" else l["chuva"]
            if v is not None:
                por_dia[l["data_hora"].date()].append(v)
        for dia, valores in por_dia.items():
            valor = sum(valores) / len(valores) if info["tipo"] == "vazao" else sum(valores)
            ja = banco.series_hidrologicas.find_one({"estacao_id": codigo, "fonte": "ANA-telemetria",
                                                     "data_hora": datetime.combine(dia, datetime.min.time())})
            if ja is None:
                banco.series_hidrologicas.insert_one(_documento(
                    codigo, info["tipo"], dia, valor, "ANA-telemetria", {"parcial": dia == date.today()}))
                gravados += 1
    return gravados
