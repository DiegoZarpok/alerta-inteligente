"""Download e leitura das séries da ANA (Hidroweb).

Usa o serviço público ServiceANA (não precisa de cadastro). Se o serviço estiver fora do ar,
dá para baixar os arquivos à mão em https://www.snirh.gov.br/hidroweb/serieshistoricas,
colocar o CSV em dados/brutos/ e rodar de novo: a leitura do CSV do Hidroweb também está aqui.

As estações são as mesmas usadas por Farias e Gomes (2023), da UESC.
"""
import calendar
import csv
import io
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import requests

from .. import config

SERVICO = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx"
TIPO = {"cota": "1", "chuva": "2", "vazao": "3"}
PREFIXO = {"cota": "Cota", "chuva": "Chuva", "vazao": "Vazao"}
# Status de cada dia na ANA: 0 = branco, 1 = real, 2 = estimado, 3 = duvidoso,
# 4 = régua seca (vazão) ou acumulado de vários dias (chuva). Nos arquivos aparecem
# também 6 e 7, sem descrição na legenda, sempre com valor 0,0 (falta de leitura).
# Só ficam os dias com status 1, 2 ou 3; status em branco mantém o valor.
STATUS_VALIDOS = {1, 2, 3}

ESTACOES = {
    # fluviométricas (vazão)
    "53180000": {"nome": "Contorno da BR-101", "tipo": "vazao", "uso": "alvo do modelo (limiar do estudo da UESC)"},
    "53170000": {"nome": "Ferradas", "tipo": "vazao", "uso": "vazão a montante"},
    # pluviométricas (chuva), as de série longa da Tabela 1 do estudo
    "01439001": {"nome": "Lomanto Junior", "tipo": "chuva", "uso": "chuva na bacia"},
    "01439002": {"nome": "Floresta Azul", "tipo": "chuva", "uso": "chuva na bacia"},
    "01439044": {"nome": "Santa Cruz da Vitória", "tipo": "chuva", "uso": "chuva na bacia"},
    "01539016": {"nome": "Fazenda Manaus", "tipo": "chuva", "uso": "chuva na bacia"},
    "01539008": {"nome": "Itajú do Colônia", "tipo": "chuva", "uso": "chuva na bacia"},
    "01539002": {"nome": "São José", "tipo": "chuva", "uso": "chuva na bacia"},
}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _numero(texto):
    if texto is None:
        return None
    texto = texto.strip().replace(",", ".")
    if texto == "":
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _data(texto):
    texto = texto.strip()
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto[:19], formato).date()
        except ValueError:
            continue
    raise ValueError(f"data em formato desconhecido: {texto!r}")


def _expandir_mes(mes_inicio, valores_por_dia, consistencia):
    """Transforma um registro mensal (Vazao01..Vazao31) em registros diários."""
    dias_no_mes = calendar.monthrange(mes_inicio.year, mes_inicio.month)[1]
    for dia in range(1, dias_no_mes + 1):
        valor = valores_por_dia.get(dia)
        if valor is not None:
            yield date(mes_inicio.year, mes_inicio.month, dia), valor, consistencia


def _valores_do_mes(campos, prefixo):
    """Pega Vazao01..Vazao31 (ou Chuva01..) descartando os dias com status inválido."""
    padrao = re.compile(rf"^{prefixo}(\d{{2}})$")
    valores = {}
    for nome, texto in campos.items():
        m = padrao.match((nome or "").strip())
        if not m:
            continue
        valor = _numero(texto)
        status = _numero(campos.get(f"{nome.strip()}Status"))
        if valor is not None and status is not None and int(status) not in STATUS_VALIDOS:
            valor = None
        valores[int(m.group(1))] = valor
    return valores


def ler_xml_serie(conteudo, variavel):
    """Lê a resposta do HidroSerieHistorica. Devolve lista de (data, valor, nivel_consistencia)."""
    raiz = ET.fromstring(conteudo)
    prefixo = PREFIXO[variavel]
    linhas = []
    for no in raiz.iter():
        if _local(no.tag) != "SerieHistorica":
            continue
        campos = {_local(f.tag): (f.text or "") for f in no}
        if "DataHora" not in campos:
            continue
        mes = _data(campos["DataHora"]).replace(day=1)
        consistencia = int(_numero(campos.get("NivelConsistencia")) or 1)
        valores = _valores_do_mes(campos, prefixo)
        linhas.extend(_expandir_mes(mes, valores, consistencia))
    return linhas


def ler_csv_hidroweb(texto, variavel):
    """Lê o CSV baixado à mão no portal Hidroweb (separado por ';' e com vírgula decimal)."""
    linhas_txt = texto.splitlines()
    inicio = next((i for i, l in enumerate(linhas_txt) if l.strip().startswith("EstacaoCodigo")), None)
    if inicio is None:
        raise ValueError("cabeçalho 'EstacaoCodigo' não encontrado no CSV")
    leitor = csv.DictReader(io.StringIO("\n".join(linhas_txt[inicio:])), delimiter=";")
    prefixo = PREFIXO[variavel]
    linhas = []
    for reg in leitor:
        texto_data = reg.get("Data") or reg.get("DataHora")
        if not texto_data:
            continue
        mes = _data(texto_data).replace(day=1)
        consistencia = int(_numero(reg.get("NivelConsistencia")) or 1)
        valores = _valores_do_mes(reg, prefixo)
        linhas.extend(_expandir_mes(mes, valores, consistencia))
    return linhas


def preferir_consistidos(linhas):
    """Quando o mesmo dia aparece bruto (1) e consistido (2), fica o consistido."""
    melhor = {}
    for dia, valor, nivel in linhas:
        if dia not in melhor or nivel > melhor[dia][1]:
            melhor[dia] = (valor, nivel)
    return [(dia, v, n) for dia, (v, n) in sorted(melhor.items())]


def _get(url, params, tentativas=4):
    erro = None
    for t in range(tentativas):
        try:
            r = requests.get(url, params=params, timeout=180)
            if r.status_code == 200:
                return r.content
            erro = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            erro = str(e)
        time.sleep(min(60, 3 * 2 ** t))
    raise ConnectionError(f"não foi possível acessar a ANA ({erro})")


def baixar_serie(codigo, variavel, ano_inicio=1960, ano_fim=None, avisar=print):
    """Baixa a série inteira em janelas de 10 anos, para não estourar o limite do serviço."""
    ano_fim = ano_fim or date.today().year
    linhas = []
    for ano in range(ano_inicio, ano_fim + 1, 10):
        fim = min(ano + 9, ano_fim)
        params = {"codEstacao": codigo, "dataInicio": f"01/01/{ano}", "dataFim": f"31/12/{fim}",
                  "tipoDados": TIPO[variavel], "nivelConsistencia": ""}
        bloco = ler_xml_serie(_get(f"{SERVICO}/HidroSerieHistorica", params), variavel)
        avisar(f"  {codigo} {ano}-{fim}: {len(bloco)} dias")
        linhas.extend(bloco)
    return preferir_consistidos(linhas)


def ler_xml_telemetria(conteudo):
    """Lê o DadosHidrometeorologicos (telemetria, leituras de 15 em 15 minutos)."""
    raiz = ET.fromstring(conteudo)
    saida = []
    for no in raiz.iter():
        if _local(no.tag) != "DadosHidrometereologicos":
            continue
        campos = {_local(f.tag): (f.text or "") for f in no}
        if not campos.get("DataHora"):
            continue
        quando = datetime.strptime(campos["DataHora"].strip()[:19], "%Y-%m-%d %H:%M:%S")
        saida.append({"data_hora": quando, "vazao": _numero(campos.get("Vazao")),
                      "nivel": _numero(campos.get("Nivel")), "chuva": _numero(campos.get("Chuva"))})
    return saida


def baixar_telemetria(codigo, dias=4):
    hoje = date.today()
    params = {"codEstacao": codigo, "dataInicio": (hoje - timedelta(days=dias)).strftime("%d/%m/%Y"),
              "dataFim": hoje.strftime("%d/%m/%Y")}
    return ler_xml_telemetria(_get(f"{SERVICO}/DadosHidrometeorologicos", params, tentativas=2))


def salvar_bruto(codigo, variavel, linhas):
    config.PASTA_BRUTOS.mkdir(parents=True, exist_ok=True)
    caminho = config.PASTA_BRUTOS / f"{codigo}_{variavel}.csv"
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["data", "valor", "nivel_consistencia"])
        for dia, valor, nivel in linhas:
            w.writerow([dia.isoformat(), "" if valor is None else valor, nivel])
    return caminho


def ler_bruto(codigo, variavel):
    """Lê o CSV já baixado; se não existir, procura um CSV do Hidroweb colocado à mão."""
    caminho = config.PASTA_BRUTOS / f"{codigo}_{variavel}.csv"
    if caminho.exists():
        with open(caminho, encoding="utf-8") as f:
            return [(date.fromisoformat(r["data"]), _numero(r["valor"]), int(r["nivel_consistencia"]))
                    for r in csv.DictReader(f)]
    p = arquivo_hidroweb(codigo, variavel)
    if p:
        return preferir_consistidos(ler_csv_hidroweb(p.read_bytes().decode("latin-1"), variavel))
    return []


def arquivo_hidroweb(codigo, variavel):
    """Procura em dados/brutos o CSV baixado à mão no Hidroweb (ex.: 53180000_Vazoes.csv, 1439001_Chuvas.csv)."""
    if not config.PASTA_BRUTOS.exists():
        return None
    proprio = f"{codigo}_{variavel}.csv"
    for p in sorted(config.PASTA_BRUTOS.glob("*.csv")):
        if p.name == proprio or codigo.lstrip("0") not in p.name:
            continue
        texto = p.read_bytes().decode("latin-1")
        if "EstacaoCodigo" in texto and f";{PREFIXO[variavel]}01;" in texto:
            return p
    return None


def montar_serie_diaria():
    """Junta todas as estações numa tabela diária: data, vazao_<cod>, chuva_<cod>."""
    import pandas as pd
    colunas = {}
    for codigo, info in ESTACOES.items():
        linhas = ler_bruto(codigo, info["tipo"])
        if linhas:
            colunas[f"{info['tipo']}_{codigo}"] = pd.Series({d: v for d, v, _ in linhas}, dtype="float64")
    if not colunas:
        raise FileNotFoundError("nenhuma série em dados/brutos. Rode antes: python cli.py baixar-dados")
    tabela = pd.DataFrame(colunas).sort_index()
    tabela.index = pd.to_datetime(tabela.index)
    tabela = tabela.asfreq("D")
    tabela.index.name = "data"
    config.PASTA_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(config.PASTA_PROCESSADOS / "serie_diaria.csv", float_format="%.3f")
    return tabela
