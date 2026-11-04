"""Chamada ao Gemini pela API REST, medindo tempo de resposta, tokens e custo de cada uso."""
import json
import time

import requests

from .. import config

# Preço por 1 milhão de tokens (US$), nível pago, conferido em ai.google.dev/gemini-api/docs/pricing (nov/2026).
# Tokens de raciocínio são cobrados como saída.
PRECOS = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-2.5-flash": (0.30, 2.50),
}
# Menor nível de raciocínio aceito por modelo (raciocínio extra custa e atrasa a resposta)
RACIOCINIO = {"gemini-3.5-flash-lite": "minimal", "gemini-3.8-flash": "low"}


class LLMIndisponivel(Exception):
    pass


class Gemini:
    def __init__(self, modelo=None, chave=None, url_base=None):
        self.modelo = modelo or config.GEMINI_MODELO
        self.chave = chave or config.GEMINI_CHAVE
        self.url_base = (url_base or config.GEMINI_URL_BASE).rstrip("/")
        if not self.chave:
            raise LLMIndisponivel("GEMINI_API_KEY não está no .env")

    def _corpo(self, sistema, usuario, json_saida, max_tokens, com_raciocinio):
        geracao = {"maxOutputTokens": max_tokens}
        if com_raciocinio and self.modelo in RACIOCINIO:
            geracao["thinkingConfig"] = {"thinkingLevel": RACIOCINIO[self.modelo]}
        if json_saida:
            geracao["responseMimeType"] = "application/json"
        return {"systemInstruction": {"parts": [{"text": sistema}]},
                "contents": [{"role": "user", "parts": [{"text": usuario}]}],
                "generationConfig": geracao}

    def gerar(self, sistema, usuario, json_saida=False, max_tokens=400):
        url = f"{self.url_base}/v1beta/models/{self.modelo}:generateContent"
        cabecalho = {"x-goog-api-key": self.chave, "Content-Type": "application/json"}
        com_raciocinio = True
        inicio = time.perf_counter()
        for tentativa in range(4):
            try:
                r = requests.post(url, headers=cabecalho, timeout=60,
                                  json=self._corpo(sistema, usuario, json_saida, max_tokens, com_raciocinio))
            except requests.RequestException as e:
                if tentativa == 3:
                    raise LLMIndisponivel(f"sem conexão com o Gemini: {e}")
                time.sleep(2 ** tentativa)
                continue
            if r.status_code == 200:
                break
            if r.status_code == 400 and "thinking" in r.text.lower() and com_raciocinio:
                com_raciocinio = False  # modelo não aceita esse nível de raciocínio: tenta sem
                continue
            if r.status_code in (429, 500, 503) and tentativa < 3:
                time.sleep(2 ** (tentativa + 1))
                continue
            raise LLMIndisponivel(f"Gemini respondeu {r.status_code}: {r.text[:300]}")
        else:
            raise LLMIndisponivel("o Gemini não respondeu depois de 4 tentativas")
        latencia = time.perf_counter() - inicio

        dados = r.json()
        candidatos = dados.get("candidates") or []
        if not candidatos:
            raise LLMIndisponivel(f"resposta sem texto: {json.dumps(dados)[:300]}")
        partes = candidatos[0].get("content", {}).get("parts", [])
        texto = "".join(p.get("text", "") for p in partes if not p.get("thought")).strip()
        uso = dados.get("usageMetadata", {})
        entrada = uso.get("promptTokenCount", 0)
        saida = uso.get("candidatesTokenCount", 0)
        raciocinio = uso.get("thoughtsTokenCount", 0)
        preco_in, preco_out = PRECOS.get(self.modelo, (None, None))
        custo = None if preco_in is None else (entrada * preco_in + (saida + raciocinio) * preco_out) / 1e6
        return {"texto": texto, "modelo": self.modelo, "tokens_entrada": entrada, "tokens_saida": saida,
                "tokens_raciocinio": raciocinio, "latencia_s": round(latencia, 3),
                "custo_usd": None if custo is None else round(custo, 7),
                "finalizacao": candidatos[0].get("finishReason")}
