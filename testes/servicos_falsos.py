"""Gemini e Telegram falsos, só para os testes automáticos (não acessam a internet)."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class EstadoGemini:
    modo = "correto"           # "correto", "numero_errado", "recusa_raciocinio"
    pedidos = []


def _texto_alerta(usuario, sistema):
    nivel = re.search(r"nivel: (\w+)|Nível de risco: (\w+)", usuario)
    nivel = (nivel.group(1) or nivel.group(2)) if nivel else "alto"
    p = int(re.search(r"(\d+)%", usuario).group(1))
    q = int(re.search(r"(\d+) m³/s", usuario).group(1))
    if EstadoGemini.modo == "numero_errado":
        p, q = min(p + 12, 99), q + 250
    nome = {"alto": "ALTO", "médio": "MÉDIO", "medio": "MÉDIO", "baixo": "BAIXO"}.get(nivel, nivel.upper())
    if "Regras:" not in sistema:  # prompt v1: texto solto, sem o nível escrito e sem o 199
        return f"Atenção moradores! Chance de cheia de {p}% nas próximas horas, com o rio em {q} m³/s. Cuidado."
    if "Responda ao morador" in usuario:
        return f"Risco {nome}. Probabilidade de cheia em 24 h: {p}%. Vazão: {q} m³/s. Mantenha o kit em local alto." + \
            (" Defesa Civil: 199" if nome != "BAIXO" else "")
    return (f"RISCO {nome} - Rio Cachoeira. Probabilidade de cheia nas próximas 24 h: {p}%. Vazão atual: {q} m³/s. "
            f"Separe documentos, eleve os móveis e siga para o Abrigo A ou B se a água subir. Defesa Civil: 199")


def _intencao(usuario):
    t = usuario.lower()
    if "morador" in t or "telefone" in t or "contato" in t:
        return {"intencao": "moradores_por_setor", "setor": "03" if "3" in t else None}
    if "relato" in t:
        return {"intencao": "relatos_recentes", "setor": None}
    if "alerta" in t:
        return {"intencao": "ultimos_alertas", "setor": None}
    if "auditoria" in t:
        return {"intencao": "auditoria_recente", "setor": None}
    if "risco" in t:
        return {"intencao": "risco_atual", "setor": None}
    return {"intencao": "fora_do_escopo", "setor": None}


class TratadorGemini(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        EstadoGemini.pedidos.append({"caminho": self.path, "corpo": corpo, "chave": self.headers.get("x-goog-api-key")})
        if EstadoGemini.modo == "recusa_raciocinio" and "thinkingConfig" in corpo.get("generationConfig", {}):
            return self._enviar(400, {"error": {"message": "thinking_level is not supported for this model"}})
        sistema = corpo["systemInstruction"]["parts"][0]["text"]
        usuario = corpo["contents"][0]["parts"][0]["text"]
        if "intencao" in sistema:
            texto = json.dumps(_intencao(usuario))
        else:
            texto = _texto_alerta(usuario, sistema)
        entrada = int(len((sistema + usuario).split()) * 1.3)
        self._enviar(200, {"candidates": [{"content": {"parts": [{"text": texto}], "role": "model"},
                                           "finishReason": "STOP"}],
                           "usageMetadata": {"promptTokenCount": entrada, "candidatesTokenCount": int(len(texto.split()) * 1.3),
                                             "thoughtsTokenCount": 0}})

    def _enviar(self, status, dados):
        b = json.dumps(dados).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class EstadoTelegram:
    enviadas = []
    fila = []


class TratadorTelegram(TratadorGemini):
    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if self.path.endswith("/sendMessage"):
            EstadoTelegram.enviadas.append(corpo)
            return self._enviar(200, {"ok": True, "result": {"message_id": len(EstadoTelegram.enviadas)}})
        self._enviar(404, {"ok": False})

    def do_GET(self):
        if "/getUpdates" in self.path:
            fila, EstadoTelegram.fila = EstadoTelegram.fila, []
            return self._enviar(200, {"ok": True, "result": fila})
        self._enviar(404, {"ok": False})


def iniciar(tratador):
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), tratador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{servidor.server_address[1]}"
