"""Bot do Telegram (usuário svc_bot). Só aceita comandos fixos; não existe conversa livre.

/start  /ajuda  /setor 03  /risco  /relato <texto>  /sair
"""
import time
from datetime import datetime, timezone

import requests

from .. import config
from ..db import conectar
from ..seguranca import anonimizar, cifrar, hash_morador, validar_setor

AJUDA = ("Alerta Inteligente - Rio Cachoeira (Itabuna)\n"
         "Comandos:\n"
         "/setor 01 a 06 - escolher o seu setor para receber alertas\n"
         "/risco - ver o risco de cheia agora\n"
         "/relato texto - contar o que você está vendo no rio ou na rua\n"
         "/sair - parar de receber alertas e apagar seus dados\n"
         "Ferramenta experimental. Em emergência ligue para a Defesa Civil: 199.")
PADRAO = "Não entendi. Este canal só responde aos comandos abaixo.\n\n" + AJUDA


class Bot:
    def __init__(self, token=None, url_base=None, banco=None, api_url=None, api_token=None):
        self.token = token or config.TELEGRAM_TOKEN
        if not self.token:
            raise SystemExit("TELEGRAM_BOT_TOKEN não está no .env")
        self.url = f"{(url_base or config.TELEGRAM_URL_BASE).rstrip('/')}/bot{self.token}"
        self.banco = banco if banco is not None else conectar("bot")
        self.api_url = (api_url or config.API_URL).rstrip("/")
        self.api_token = api_token or config.API_TOKEN
        self.deslocamento = 0

    def enviar(self, chat_id, texto):
        requests.post(f"{self.url}/sendMessage", json={"chat_id": chat_id, "text": texto[:4000]}, timeout=20)

    def _auditar(self, acao, colecao, morador, detalhe):
        self.banco.auditoria.insert_one({"data_hora": datetime.now(timezone.utc), "usuario": config.USUARIOS["bot"],
                                         "acao": acao, "colecao": colecao, "solicitante": f"morador:{morador[:8]}",
                                         "ip": "127.0.0.1", "detalhe": detalhe})

    def tratar(self, chat_id, texto):
        """Recebe a mensagem e devolve a resposta (separado do Telegram para poder testar)."""
        texto = (texto or "").strip()
        comando, _, resto = texto.partition(" ")
        comando = comando.split("@")[0].lower()
        morador = hash_morador(chat_id)

        if comando in ("/start", "/ajuda", "/help"):
            return AJUDA
        if comando == "/setor":
            setor = validar_setor(resto)
            if not setor:
                return "Setor inválido. Envie, por exemplo: /setor 03 (setores de 01 a 06)."
            self.banco.moradores.update_one(
                {"chat_hash": morador},
                {"$set": {"setor": setor, "ativo": True},
                 "$setOnInsert": {"chat_hash": morador, "chat_cifrado": cifrar(chat_id),
                                  "inscrito_em": datetime.now(timezone.utc)}},
                upsert=True)
            self._auditar("upsert", "moradores", morador, f"inscrição no {setor}")
            return f"Pronto. Você vai receber os alertas do {setor}."
        if comando == "/risco":
            try:
                r = requests.get(f"{self.api_url}/risco", params={"solicitante": morador[:8]},
                                 headers={"X-Token": self.api_token}, timeout=90)
                r.raise_for_status()
                return r.json()["texto"]
            except Exception:  # noqa: BLE001
                return "Não consegui consultar o risco agora. Tente de novo em alguns minutos. Emergência: 199."
        if comando == "/relato":
            if len(resto) < 5:
                return "Escreva o relato depois do comando. Exemplo: /relato a água chegou na calçada."
            atual = self.banco.moradores.find_one({"chat_hash": morador}, {"setor": 1})
            self.banco.relatos.insert_one({
                "morador_hash": morador, "recebido_em": datetime.now(timezone.utc),
                "setor": (atual or {}).get("setor", "não informado"),
                "texto_anonimizado": anonimizar(resto[:1000]), "texto_cifrado": cifrar(resto[:1000]), "classe": None})
            self._auditar("insert", "relatos", morador, "relato recebido")
            return "Relato recebido. Obrigado. Se houver risco à vida, ligue 199."
        if comando == "/sair":
            self.banco.moradores.delete_many({"chat_hash": morador})
            self.banco.relatos.delete_many({"morador_hash": morador})
            self._auditar("delete", "moradores, relatos", morador, "pedido de exclusão (/sair)")
            return "Seus dados foram apagados e você não vai mais receber alertas."
        return PADRAO

    def rodar(self):
        print("Bot do Alerta Inteligente rodando. Deixe esta janela aberta. Para parar: Ctrl + C")
        while True:
            try:
                r = requests.get(f"{self.url}/getUpdates", params={"timeout": 25, "offset": self.deslocamento},
                                 timeout=35)
                for atualizacao in r.json().get("result", []):
                    self.deslocamento = atualizacao["update_id"] + 1
                    msg = atualizacao.get("message") or {}
                    if "text" in msg:
                        resposta = self.tratar(msg["chat"]["id"], msg["text"])
                        self.enviar(msg["chat"]["id"], resposta)
            except KeyboardInterrupt:
                print("Bot encerrado.")
                return
            except requests.RequestException as erro:
                # só o tipo do erro: a mensagem completa traz a URL com o token do bot
                print(f"[bot] sem conexão com o Telegram ({type(erro).__name__}); tentando de novo em 5 s")
                time.sleep(5)
