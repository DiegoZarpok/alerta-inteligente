"""Testes das partes isoladas: segurança, leitura da ANA, limiares, validador, RAG e Gemini."""
import json
import subprocess
from datetime import date

import pytest

from src import config, seguranca
from src.coleta import ana
from src.ia import rag
from src.ia.llm import Gemini, LLMIndisponivel
from src.ia.validador import validar
from src.modelo import limiares
from testes import servicos_falsos as falsos

XML_ANA = """<?xml version="1.0" encoding="utf-8"?>
<DataTable xmlns="http://MRCS/">
  <diffgr:diffgram xmlns:msdata="urn:schemas-microsoft-com:xml-msdata" xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
    <DocumentElement xmlns="">
      <SerieHistorica diffgr:id="SerieHistorica1" msdata:rowOrder="0">
        <EstacaoCodigo>53180000</EstacaoCodigo><NivelConsistencia>1</NivelConsistencia>
        <DataHora>2007-02-01 00:00:00</DataHora><MediaDiaria>1</MediaDiaria>
        <Vazao01>10.5</Vazao01><Vazao02>11.0</Vazao02><Vazao28>900.25</Vazao28><Vazao29>5</Vazao29>
        <Vazao01Status>1</Vazao01Status>
      </SerieHistorica>
      <SerieHistorica diffgr:id="SerieHistorica2" msdata:rowOrder="1">
        <EstacaoCodigo>53180000</EstacaoCodigo><NivelConsistencia>2</NivelConsistencia>
        <DataHora>2007-02-01 00:00:00</DataHora>
        <Vazao01>10.7</Vazao01><Vazao02></Vazao02>
      </SerieHistorica>
    </DocumentElement>
  </diffgr:diffgram>
</DataTable>"""

CSV_HIDROWEB = ("//  ANA - Agência Nacional de Águas\n//  Sistema de Informações Hidrológicas\n\n"
                "EstacaoCodigo;NivelConsistencia;Data;TipoMedicaoChuvas;Maxima;Total;"
                + ";".join(f"Chuva{d:02d}" for d in range(1, 32)) + ";"
                + ";".join(f"Chuva{d:02d}Status" for d in range(1, 32)) + "\n"
                "1439001;2;01/03/2007;1;55,2;210,4;" + ";".join(["3,5", "0", "55,2"] + [""] * 28) + ";"
                + ";".join(["1"] * 31) + "\n")


def test_hash_e_criptografia():
    h = seguranca.hash_morador(123456)
    assert len(h) == 64 and h == seguranca.hash_morador("123456")
    c = seguranca.cifrar("texto secreto")
    assert c.count(".") == 2 and "texto" not in c
    assert seguranca.decifrar(c) == "texto secreto"


def test_criptografia_compativel_com_o_script_js():
    """O mongosh (02_carga_inicial.js) e o Python precisam ler o que o outro gravou."""
    js = ("const c=require('crypto');const k=Buffer.from(process.env.ALERTA_CHAVE,'hex');"
          "const iv=c.randomBytes(12);const ci=c.createCipheriv('aes-256-gcm',k,iv);"
          "const d=Buffer.concat([ci.update('cifrado no node','utf8'),ci.final()]);"
          "console.log([iv.toString('base64'),ci.getAuthTag().toString('base64'),d.toString('base64')].join('.'))")
    cifrado_js = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout.strip()
    assert seguranca.decifrar(cifrado_js) == "cifrado no node"
    cifrado_py = seguranca.cifrar("cifrado no python")
    js2 = ("const c=require('crypto');const [iv,t,d]=process.argv[1].split('.').map(x=>Buffer.from(x,'base64'));"
           "const de=c.createDecipheriv('aes-256-gcm',Buffer.from(process.env.ALERTA_CHAVE,'hex'),iv);"
           "de.setAuthTag(t);console.log(Buffer.concat([de.update(d),de.final()]).toString('utf8'))")
    assert subprocess.run(["node", "-e", js2, cifrado_py], capture_output=True, text=True,
                          check=True).stdout.strip() == "cifrado no python"


def test_anonimizacao():
    t = seguranca.anonimizar("Meu nome é Carlos Souza, moro na Rua das Flores, 120, tel (73) 99812-3344, a@b.com")
    assert "Carlos" not in t and "99812" not in t and "Flores" not in t and "a@b.com" not in t
    assert "[NOME]" in t and "[TELEFONE]" in t and "[ENDERECO]" in t and "[EMAIL]" in t
    assert seguranca.anonimizar("Rua alagada aqui") == "Rua alagada aqui"


@pytest.mark.parametrize("entrada,esperado", [
    ("3", "Setor Ribeirinho 03"), ("03", "Setor Ribeirinho 03"), (" setor 6 ", "Setor Ribeirinho 06"),
    ('{"$ne": null}', None), ("7", None), ("1; db.dropDatabase()", None), ("", None), ({"$gt": ""}, None)])
def test_validar_setor_bloqueia_injecao(entrada, esperado):
    assert seguranca.validar_setor(entrada) == esperado


def test_leitura_xml_da_ana_prefere_consistido():
    linhas = ana.preferir_consistidos(ana.ler_xml_serie(XML_ANA, "vazao"))
    dias = {d: (v, n) for d, v, n in linhas}
    assert dias[date(2007, 2, 1)] == (10.7, 2)          # o consistido (2) vence o bruto (1)
    assert dias[date(2007, 2, 2)] == (11.0, 1)          # dia vazio no consistido: fica o bruto
    assert dias[date(2007, 2, 28)] == (900.25, 1)
    assert len(linhas) == 3                             # Vazao29 de fevereiro de 2007 é ignorada


def test_leitura_csv_do_hidroweb():
    linhas = ana.ler_csv_hidroweb(CSV_HIDROWEB, "chuva")
    dias = {d: v for d, v, _ in linhas}
    assert dias[date(2007, 3, 1)] == 3.5 and dias[date(2007, 3, 3)] == 55.2 and dias[date(2007, 3, 2)] == 0.0
    assert len(dias) == 3


def test_limiares_reproduzem_o_estudo_da_uesc():
    for tr, (q, _) in limiares.TABELA_UESC_CONTORNO.items():
        assert abs(limiares.vazao_para_tr(tr) - q) / q < 0.01
    assert 900 < limiares.vazao_para_tr(3) < 960
    assert 50 < limiares.tr_da_vazao(2430) < 60


def test_validador():
    dados = {"nivel": "alto", "probabilidade_pct": 71, "vazao_m3s": 845, "limiar_m3s": 929.9, "abrigos": ["A", "B", "C"]}
    bom = "RISCO ALTO - Rio Cachoeira. Probabilidade de cheia: 71%. Vazão atual: 845 m³/s. Vá ao Abrigo A. Defesa Civil: 199"
    assert validar(bom, dados) == (True, [])
    ok, problemas = validar(bom.replace("71%", "80%").replace("845", "1.200").replace("Abrigo A", "Abrigo Z"), dados)
    assert not ok and len(problemas) >= 4
    assert not validar("Atenção! Chance de 71% com o rio em 845 m³/s.", dados)[0]  # sem nível e sem 199
    assert validar("RISCO ALTO 71% 845 m3/s, acima do limiar de 930 m³/s. Defesa Civil: 199", dados)[0]


def test_divisao_em_trechos():
    texto = "\n\n".join(" ".join(f"palavra{i}_{j}" for j in range(120)) for i in range(6))
    trechos = rag.dividir(texto)
    assert len(trechos) >= 2
    assert all(len(t.split()) <= int(400 / 1.3) for t in trechos)
    assert trechos[0].split()[-10:] == trechos[1].split()[:10] or set(trechos[0].split()[-38:]) & set(trechos[1].split())
    todos = rag.preparar_trechos()
    assert len({t["arquivo"] for t in todos}) == 24
    assert any("alto" in t["niveis"] for t in todos) and all(t["niveis"] for t in todos)


def test_gemini_mede_tokens_custo_e_tenta_sem_raciocinio():
    servidor, url = falsos.iniciar(falsos.TratadorGemini)
    try:
        falsos.EstadoGemini.modo = "recusa_raciocinio"
        g = Gemini(modelo="gemini-3.5-flash-lite", chave="x", url_base=url)
        r = g.gerar("Regras:\n1. ...", "DADOS\nnivel: alto\nprobabilidade_cheia_24h: 71%\nvazao_atual: 845 m³/s\nEscreva")
        assert "71%" in r["texto"] and r["tokens_entrada"] > 0 and r["custo_usd"] > 0
        assert "thinkingConfig" not in falsos.EstadoGemini.pedidos[-1]["corpo"]["generationConfig"]
        assert falsos.EstadoGemini.pedidos[-1]["chave"] == "x"
        falsos.EstadoGemini.modo = "correto"
        r = g.gerar("Regras:", "DADOS\nnivel: medio\nprobabilidade_cheia_24h: 40%\nvazao_atual: 500 m³/s")
        assert falsos.EstadoGemini.pedidos[-1]["corpo"]["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "minimal"
    finally:
        servidor.shutdown()
    with pytest.raises(LLMIndisponivel):
        Gemini(modelo="gemini-3.5-flash-lite", chave="x", url_base="http://127.0.0.1:9").gerar("a", "b")


def test_prompts_versionados_tem_as_secoes():
    from src.ia.alerta import carregar_prompt
    for nome, versao in [("alerta", "v1"), ("alerta", "v2"), ("risco", "v1"), ("intencao", "v1"),
                         ("classificar_relato", "v1")]:
        sistema, usuario = carregar_prompt(nome, versao)
        assert sistema and usuario


def test_fluxo_n8n_bem_formado():
    fluxo = json.loads((config.RAIZ / "n8n" / "fluxo_alerta.json").read_text(encoding="utf-8"))
    nomes = {n["name"] for n in fluxo["nodes"]}
    for origem, saidas in fluxo["connections"].items():
        assert origem in nomes
        assert all(d["node"] in nomes for ramo in saidas["main"] for d in ramo)
    tipos = {n["type"] for n in fluxo["nodes"]}
    assert {"n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.httpRequest", "n8n-nodes-base.telegram",
            "n8n-nodes-base.mongoDb"} <= tipos
    texto = json.dumps(fluxo)
    assert "token-de-teste" not in texto and "senha" not in texto.lower()
