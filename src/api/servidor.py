"""API local (sem tela) chamada pelo n8n e pelo bot. Só aceita pedidos com o cabeçalho X-Token.

POST /ciclo   coleta (ou avança a reprodução) e calcula o risco do dia
POST /alerta  gera o texto do alerta com RAG + Gemini + validador
GET  /risco   resposta curta para o comando /risco do bot
GET  /saude   verificação simples
"""
import hmac
import json
import traceback
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .. import config
from ..ia import alerta
from ..modelo.prever import DadosInsuficientes, prever

ESTADO = config.PASTA_RESULTADOS / "estado_operacao.json"


def _ler_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def _salvar_estado(estado):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def ciclo(corpo):
    estado = _ler_estado()
    modo = corpo.get("modo") or config.MODO_OPERACAO
    if modo == "reproducao":
        if corpo.get("reiniciar") or "proxima_data" not in estado:
            estado["proxima_data"] = config.REPRODUCAO_INICIO
        dia = date.fromisoformat(corpo.get("data") or estado["proxima_data"])
        estado["proxima_data"] = (dia + timedelta(days=1)).isoformat()
    else:
        ultimo = estado.get("ultimo_ciclo")
        if ultimo and ultimo["nivel_risco"] == "baixo":
            minutos = (datetime.now() - datetime.fromisoformat(ultimo["quando"])).total_seconds() / 60
            if minutos < config.INTERVALO_MIN_BAIXO and not corpo.get("forcar"):
                return {"pulado": True, "enviar_alerta": False, "motivo": f"risco baixo há {minutos:.0f} min"}
        from ..coleta.carregar import coletar_tempo_real
        coletar_tempo_real(avisar=lambda *_: None)
        dia = date.today()
    try:
        r = prever(dia, fonte="mongo", registrar=True, modo=modo)
    except DadosInsuficientes as erro:
        _salvar_estado(estado)
        return {"enviar_alerta": False, "nivel_risco": "indisponivel", "data_referencia": dia.isoformat(),
                "erro": str(erro)}
    r["enviar_alerta"] = r["nivel_risco"] in ("medio", "alto")
    estado["ultimo_ciclo"] = {"quando": datetime.now().isoformat(timespec="seconds"),
                              "nivel_risco": r["nivel_risco"], "data_referencia": r["data_referencia"]}
    _salvar_estado(estado)
    return r


class Tratador(BaseHTTPRequestHandler):
    server_version = "AlertaInteligente/1.0"

    def log_message(self, formato, *args):  # registro curto no terminal, sem cabeçalhos
        print(f"[api] {self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}")

    def _responder(self, status, dados):
        corpo = json.dumps(dados, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _autorizado(self):
        recebido = self.headers.get("X-Token", "")
        return bool(config.API_TOKEN) and hmac.compare_digest(recebido, config.API_TOKEN)

    def _corpo(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho == 0:
            return {}
        dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
        if not isinstance(dados, dict):
            raise ValueError("o corpo precisa ser um objeto JSON")
        return dados

    def _executar(self, funcao):
        if not self._autorizado():
            return self._responder(401, {"erro": "token ausente ou inválido"})
        try:
            self._responder(200, funcao())
        except (ValueError, LookupError) as erro:
            self._responder(400, {"erro": str(erro)})
        except Exception as erro:  # noqa: BLE001
            traceback.print_exc()
            self._responder(500, {"erro": f"{type(erro).__name__}: {erro}"})

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/saude":
            return self._responder(200, {"ok": True, "modo": config.MODO_OPERACAO})
        if url.path == "/risco":
            solicitante = parse_qs(url.query).get("solicitante", ["bot"])[0][:40]
            return self._executar(lambda: {"texto": alerta.responder_risco(f"bot:{solicitante}")})
        self._responder(404, {"erro": "rota não encontrada"})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/ciclo":
            return self._executar(lambda: ciclo(self._corpo()))
        if url.path == "/alerta":
            def gerar():
                corpo = self._corpo()
                return alerta.gerar_alerta(corpo.get("previsao_id"), solicitante=corpo.get("solicitante", "n8n"))
            return self._executar(gerar)
        self._responder(404, {"erro": "rota não encontrada"})


def iniciar():
    if not config.API_TOKEN:
        raise SystemExit("Defina API_TOKEN no .env antes de iniciar a API (python cli.py configurar)")
    servidor = ThreadingHTTPServer((config.API_HOST, config.API_PORTA), Tratador)
    print(f"API do Alerta Inteligente em http://{config.API_HOST}:{config.API_PORTA} (modo {config.MODO_OPERACAO})")
    print("Deixe esta janela aberta. Para parar: Ctrl + C")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("API encerrada.")
