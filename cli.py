"""Alerta Inteligente: comandos do projeto e terminal do operador.

Uso: python cli.py <comando>     (python cli.py ajuda mostra a lista)
"""
import argparse
import getpass
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ENV = RAIZ / ".env"
SCRIPTS_BANCO = {"criar": "01_criar_banco.js", "carga": "02_carga_inicial.js", "papeis": "03_papeis_usuarios.js",
                 "volume": "04_gerar_volume.js", "consultas-lentas": "05_consultas_lentas.js"}


def _ler_env():
    valores = {}
    if ENV.exists():
        for linha in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                valores[k.strip()] = v.strip()
    return valores


def configurar(_):
    """Cria o .env com senhas e chaves aleatórias. Não apaga o que já estiver preenchido."""
    atual = _ler_env()
    novos = {
        "MONGODB_HOST": "localhost:27017", "MONGODB_BANCO": "alerta_inteligente",
        "MONGODB_ADMIN_USUARIO": "admin", "MONGODB_ADMIN_SENHA": secrets.token_urlsafe(18),
        "SENHA_SVC_COLETA": secrets.token_urlsafe(18), "SENHA_SVC_MODELO": secrets.token_urlsafe(18),
        "SENHA_SVC_IA": secrets.token_urlsafe(18), "SENHA_SVC_CLASSIFICADOR": secrets.token_urlsafe(18),
        "SENHA_SVC_BOT": secrets.token_urlsafe(18), "SENHA_SVC_N8N": secrets.token_urlsafe(18),
        "SENHA_OPERADOR": secrets.token_urlsafe(18), "SENHA_AUDITOR": secrets.token_urlsafe(18),
        "ALERTA_CHAVE": secrets.token_hex(32), "ALERTA_SAL": secrets.token_urlsafe(24),
        "API_TOKEN": secrets.token_urlsafe(32),
        "GEMINI_MODELO": "gemini-3.5-flash-lite", "PROMPT_ALERTA_VERSAO": "v2",
        "MODO_OPERACAO": "reproducao", "REPRODUCAO_INICIO": "2007-12-01",
        "LIMIAR_TR_ALVO": "3", "ANO_CORTE_TREINO": "2000",
    }
    for chave, pergunta in [("GEMINI_API_KEY", "Cole a chave do Gemini (ou Enter para preencher depois): "),
                            ("TELEGRAM_BOT_TOKEN", "Cole o token do bot do Telegram (ou Enter para depois): ")]:
        if not atual.get(chave):
            novos[chave] = input(pergunta).strip()
    novos.setdefault("TELEGRAM_CHAT_ALERTAS", "")
    final = {**novos, **{k: v for k, v in atual.items() if v}}
    linhas = ["# Arquivo gerado por: python cli.py configurar", "# NUNCA envie este arquivo para o GitHub.", ""]
    linhas += [f"{k}={v}" for k, v in final.items()]
    ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f".env salvo em {ENV} ({len(final)} variáveis). Ele já está no .gitignore.")


def _mongosh():
    caminho = shutil.which("mongosh")
    if not caminho:
        sys.exit("mongosh não encontrado. Instale o MongoDB Shell e abra um terminal novo.")
    return caminho


def criar_admin(_):
    """Cria o usuário administrador (antes de ligar a autenticação)."""
    from pymongo import MongoClient
    from src import config
    if not config.SENHAS["admin"]:
        sys.exit("Rode antes: python cli.py configurar")
    cliente = MongoClient(f"mongodb://{config.MONGO_HOST}/", serverSelectionTimeoutMS=5000)
    admin = cliente.admin
    if admin.command("usersInfo", config.USUARIOS["admin"])["users"]:
        print(f"O usuário {config.USUARIOS['admin']} já existe.")
        return
    admin.command("createUser", config.USUARIOS["admin"], pwd=config.SENHAS["admin"],
                  roles=[{"role": "root", "db": "admin"}])
    print(f"Usuário {config.USUARIOS['admin']} criado. Agora ligue a autenticação no mongod.cfg (passo do guia).")


def banco(args):
    """Roda um script do mongosh da pasta banco/ como administrador, com as variáveis do .env."""
    from src import config
    nome = SCRIPTS_BANCO[args.script]
    uri = (f"mongodb://{config.USUARIOS['admin']}:{config.SENHAS['admin']}@{config.MONGO_HOST}/"
           f"{config.BANCO}?authSource=admin")
    ambiente = {**os.environ, **_ler_env()}
    print(f"Rodando banco/{nome} ...")
    r = subprocess.run([_mongosh(), uri, "--quiet", "--file", str(RAIZ / "banco" / nome)], cwd=RAIZ, env=ambiente)
    sys.exit(r.returncode)


def baixar_dados(_):
    from src.coleta import ana
    print("Baixando as séries da ANA (pode levar alguns minutos)...")
    for codigo, info in ana.ESTACOES.items():
        print(f"{codigo} {info['nome']} ({info['tipo']})")
        manual = ana.arquivo_hidroweb(codigo, info["tipo"])
        if manual:
            validos = [l for l in ana.ler_bruto(codigo, info["tipo"]) if l[1] is not None]
            print(f"  usando o CSV do Hidroweb {manual.name}: {len(validos)} dias com dado, "
                  f"de {validos[0][0]} a {validos[-1][0]}")
            continue
        try:
            linhas = ana.baixar_serie(codigo, info["tipo"])
            if not linhas and codigo.startswith("0"):
                linhas = ana.baixar_serie(codigo.lstrip("0"), info["tipo"])
        except ConnectionError as erro:
            print(f"  {erro}. Baixe o CSV no Hidroweb e coloque em dados/brutos/ (passo alternativo do guia).")
            continue
        validos = [l for l in linhas if l[1] is not None]
        caminho = ana.salvar_bruto(codigo, info["tipo"], linhas)
        if validos:
            print(f"  {len(validos)} dias com dado, de {validos[0][0]} a {validos[-1][0]} -> {caminho.name}")
        else:
            print("  nenhum dado retornado")
    tabela = ana.montar_serie_diaria()
    print(f"Série diária montada: {tabela.index.min().date()} a {tabela.index.max().date()}, {len(tabela)} dias")
    print("Arquivo: dados/processados/serie_diaria.csv")


def carregar_dados(_):
    from src.coleta.carregar import carregar_series
    print(f"{carregar_series()} leituras novas gravadas em series_hidrologicas.")


def limiares_cmd(_):
    from src.modelo import limiares
    print(limiares.resumo())


def eventos_cmd(_):
    import pandas as pd
    from src import config
    from src.modelo import limiares
    from src.modelo.dados import eventos
    tabela = pd.read_csv(config.PASTA_PROCESSADOS / "serie_diaria.csv", index_col="data", parse_dates=True)
    limiar = limiares.vazao_para_tr(config.TR_ALVO)
    lista = eventos(tabela[f"vazao_{config.ESTACAO_ALVO}"], limiar)
    print(f"Cheias acima de {limiar:.0f} m³/s na estação Contorno da BR-101: {len(lista)}")
    for e in sorted(lista, key=lambda e: -e["pico_m3s"]):
        print(f"  {e['inicio']} a {e['fim']}: pico de {e['pico_m3s']:.0f} m³/s em {e['dia_pico']} "
              f"(TR de {e['tr_anos']} anos)")


def treinar_cmd(args):
    from src.modelo.treinar import treinar
    treinar(fonte=args.fonte)


def prever_cmd(args):
    from src.modelo.prever import prever
    r = prever(args.data, fonte=args.fonte, registrar=args.fonte == "mongo")
    for k, v in r.items():
        print(f"  {k}: {v}")


def indexar(_):
    from src.db import conectar
    from src.ia import rag
    rag.indexar(conectar("admin"))


def servidor(_):
    from src.api.servidor import iniciar
    iniciar()


def bot(_):
    from src.bot.bot import Bot
    Bot().rodar()


def telegram_chat_id(_):
    """Mostra o id dos grupos em que o bot recebeu mensagem (para TELEGRAM_CHAT_ALERTAS)."""
    import requests
    from src import config
    r = requests.get(f"{config.TELEGRAM_URL_BASE}/bot{config.TELEGRAM_TOKEN}/getUpdates", timeout=20).json()
    vistos = {}
    for u in r.get("result", []):
        chat = (u.get("message") or u.get("my_chat_member") or {}).get("chat")
        if chat:
            vistos[chat["id"]] = chat.get("title") or chat.get("first_name")
    if not vistos:
        print("Nenhuma mensagem encontrada. Mande uma mensagem no grupo (com o bot dentro) e rode de novo.")
    for cid, nome in vistos.items():
        print(f"  {nome}: {cid}")


def classificar(_):
    from src.ia.classificador import classificar_pendentes
    classificar_pendentes()


def testar_permissoes(_):
    from src.permissoes import testar
    testar()


def casos(_):
    from src.casos import rodar
    rodar()


def avaliar_prompts(_):
    from src.avaliacao import avaliar_prompts as av
    av()


def custo_latencia(args):
    from src.avaliacao import medir_custo_latencia
    medir_custo_latencia(repeticoes=args.repeticoes, modelos=args.modelos)


def consulta(args):
    """Terminal do operador: pergunta em linguagem natural, respondida com a SUA permissão no banco."""
    from pymongo.errors import OperationFailure
    from src import config
    from src.ia.consulta import consultar
    if args.senha_do_env:
        # demonstração: usa a senha guardada no .env para esse usuário (a conexão continua sendo a dele)
        perfil = next((p for p, u in config.USUARIOS.items() if u == args.usuario), None)
        senha = config.SENHAS.get(perfil) if perfil else None
        if not senha:
            sys.exit(f"Não há senha de {args.usuario} no .env.")
    else:
        # no Windows, colar com Ctrl+V aqui pode não funcionar: digite a senha ou use --senha-do-env
        senha = getpass.getpass(f"Senha de {args.usuario}: ")
    try:
        r = consultar(args.usuario, senha, args.pergunta)
    except OperationFailure as erro:
        if erro.code == 18:
            sys.exit(f"Senha incorreta para {args.usuario}. Nada foi consultado.")
        raise
    print(f"Intenção entendida: {r['intencao']} ({r['metodo_intencao']})")
    print(r["mensagem"])
    for linha in r["linhas"]:
        print("  - " + " | ".join(f"{k}: {v}" for k, v in linha.items()))


def auditoria(args):
    """Mostra os últimos registros de auditoria (entra como auditor, pela view mascarada)."""
    from src.db import conectar
    banco_aud = conectar("auditor")
    from datetime import timezone
    print("quando (horário local) | serviço            | pedido por             | ação         | resultado | coleção     | detalhe")
    for d in banco_aud.vw_auditoria_mascarada.find({}).sort("data_hora", -1).limit(args.n):
        # o MongoDB guarda em UTC; aqui mostra no horário do computador
        quando = d["data_hora"].replace(tzinfo=timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S")
        pedido = str(d.get("solicitante") or "-")[:22]
        permitido = d.get("permitido")
        resultado = "-" if permitido is None else ("permitido" if permitido else "NEGADO")
        print(f"{quando}   | {d['usuario']:<18} | {pedido:<22} | {d['acao']:<12} | {resultado:<9} | "
              f"{d['colecao'][:11]:<11} | {str(d.get('detalhe', ''))[:60]}")


def status(_):
    from src.db import conectar
    b = conectar("operador")
    p = b.previsoes.find_one(sort=[("data_hora", -1)])
    a = b.alertas.find_one(sort=[("enviado_em", -1)])
    print("Última previsão:", "nenhuma" if not p else
          f"{p['data_referencia'].date()} | nível {p['nivel_risco']} | P = {p['probabilidade']:.2f}")
    print("Último alerta:  ", "nenhum" if not a else f"{a['enviado_em']:%d/%m/%Y %H:%M} | {a['texto'][:90]}")


def main():
    p = argparse.ArgumentParser(description="Alerta Inteligente - Rio Cachoeira (Itabuna)")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("configurar", help="cria o .env com senhas e chaves").set_defaults(f=configurar)
    sub.add_parser("criar-admin", help="cria o administrador do MongoDB").set_defaults(f=criar_admin)
    b = sub.add_parser("banco", help="roda um script da pasta banco/ (criar, carga, papeis, volume, consultas-lentas)")
    b.add_argument("script", choices=list(SCRIPTS_BANCO))
    b.set_defaults(f=banco)
    sub.add_parser("baixar-dados", help="baixa as séries da ANA").set_defaults(f=baixar_dados)
    sub.add_parser("carregar-dados", help="grava as séries no MongoDB").set_defaults(f=carregar_dados)
    sub.add_parser("limiares", help="mostra os limiares do estudo da UESC").set_defaults(f=limiares_cmd)
    sub.add_parser("eventos", help="lista as cheias da série").set_defaults(f=eventos_cmd)
    t = sub.add_parser("treinar", help="treina e avalia o modelo")
    t.add_argument("--fonte", choices=["mongo", "csv"], default="mongo")
    t.set_defaults(f=treinar_cmd)
    pv = sub.add_parser("prever", help="calcula o risco de um dia")
    pv.add_argument("data", help="AAAA-MM-DD")
    pv.add_argument("--fonte", choices=["mongo", "csv"], default="mongo")
    pv.set_defaults(f=prever_cmd)
    sub.add_parser("indexar-documentos", help="monta a base do RAG no MongoDB").set_defaults(f=indexar)
    sub.add_parser("servidor", help="inicia a API local usada pelo n8n e pelo bot").set_defaults(f=servidor)
    sub.add_parser("bot", help="inicia o bot do Telegram").set_defaults(f=bot)
    sub.add_parser("telegram-chat-id", help="mostra o id do grupo de alertas").set_defaults(f=telegram_chat_id)
    sub.add_parser("classificar", help="classifica relatos pendentes").set_defaults(f=classificar)
    sub.add_parser("testar-permissoes", help="testa o acesso de cada usuário").set_defaults(f=testar_permissoes)
    sub.add_parser("casos", help="roda os casos de teste da IA").set_defaults(f=casos)
    sub.add_parser("avaliar-prompts", help="compara as versões do prompt").set_defaults(f=avaliar_prompts)
    c = sub.add_parser("custo-latencia", help="mede custo e tempo de resposta")
    c.add_argument("--repeticoes", type=int, default=20)
    c.add_argument("--modelos", nargs="*", default=None)
    c.set_defaults(f=custo_latencia)
    q = sub.add_parser("consulta", help="pergunta ao sistema com a sua permissão no banco")
    q.add_argument("--usuario", required=True)
    q.add_argument("--senha-do-env", action="store_true", help="usa a senha desse usuário guardada no .env")
    q.add_argument("pergunta")
    q.set_defaults(f=consulta)
    a = sub.add_parser("auditoria", help="mostra os últimos registros de auditoria")
    a.add_argument("-n", type=int, default=20)
    a.set_defaults(f=auditoria)
    sub.add_parser("status", help="última previsão e último alerta").set_defaults(f=status)
    args = p.parse_args()
    try:
        args.f(args)
    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        try:
            from src.db import fechar_tudo
            fechar_tudo()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
