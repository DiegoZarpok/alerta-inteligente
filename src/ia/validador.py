"""Confere o texto gerado pelo Gemini antes de qualquer envio.

O nível, a probabilidade e a vazão têm de ser exatamente os calculados pelo modelo. Se algo não
bater, a mensagem é bloqueada e o sistema usa o texto padrão (documento 24 da base).
"""
import re
import unicodedata

PALAVRA_NIVEL = {"alto": ["alto"], "medio": ["medio", "atencao"], "baixo": ["baixo"]}
MAX_CARACTERES = 700


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def _inteiro(texto):
    return int(round(float(texto.replace(".", "").replace(",", "."))))


def validar(texto, dados):
    """dados: nivel, probabilidade_pct, vazao_m3s, limiar_m3s (opcional), abrigos (opcional)."""
    problemas = []
    simples = _sem_acento(texto)

    if not any(p in simples for p in PALAVRA_NIVEL[dados["nivel"]]):
        problemas.append(f"não cita o nível de risco ({dados['nivel']})")

    porcentagens = [_inteiro(p) for p in re.findall(r"(\d+(?:[.,]\d+)?)\s*%", texto)]
    if dados["probabilidade_pct"] not in porcentagens:
        problemas.append(f"não traz a probabilidade correta ({dados['probabilidade_pct']}%)")
    outras = sorted({p for p in porcentagens if p != dados["probabilidade_pct"]})
    if outras:
        problemas.append(f"porcentagem diferente da calculada: {outras}")

    vazoes = [_inteiro(v) for v in re.findall(r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)\s*m(?:³|3)\s*/\s*s", texto)]
    permitidas = {int(round(dados["vazao_m3s"]))}
    if dados.get("limiar_m3s"):
        permitidas.add(int(round(dados["limiar_m3s"])))
    if int(round(dados["vazao_m3s"])) not in vazoes:
        problemas.append(f"não traz a vazão correta ({int(round(dados['vazao_m3s']))} m³/s)")
    erradas = sorted({v for v in vazoes if v not in permitidas})
    if erradas:
        problemas.append(f"vazão diferente da calculada: {erradas}")

    if dados["nivel"] != "baixo" and "199" not in texto:
        problemas.append("não traz o telefone da Defesa Civil (199)")

    abrigos = set(re.findall(r"Abrigo\s+([A-Z])\b", texto))
    if dados.get("abrigos") is not None and not abrigos <= set(dados["abrigos"]):
        problemas.append(f"abrigo que não está nos documentos: {sorted(abrigos - set(dados['abrigos']))}")

    if re.search(r"https?://|www\.", texto):
        problemas.append("contém link")
    if len(texto) > MAX_CARACTERES:
        problemas.append(f"texto longo demais ({len(texto)} caracteres)")
    return (not problemas), problemas
