"""Conexões com o MongoDB. Cada parte do sistema usa o próprio usuário e papel."""
from urllib.parse import quote_plus

from pymongo import MongoClient
from pymongo.errors import OperationFailure

from . import config

_clientes = {}


class SemPermissao(Exception):
    """O MongoDB recusou a operação para o usuário conectado."""


def _uri(usuario, senha, auth_db):
    if config.MONGO_SEM_AUTH:
        return f"mongodb://{config.MONGO_HOST}/"
    return (f"mongodb://{quote_plus(usuario)}:{quote_plus(senha)}@{config.MONGO_HOST}/"
            f"?authSource={auth_db}")


def conectar(perfil):
    """Devolve o banco aberto com o usuário do perfil (coleta, modelo, ia, bot...)."""
    if perfil not in _clientes:
        usuario = config.USUARIOS[perfil]
        senha = config.SENHAS.get(perfil)
        if not senha and not config.MONGO_SEM_AUTH:
            raise RuntimeError(f"Senha do perfil '{perfil}' não está no .env")
        auth_db = "admin" if perfil == "admin" else config.BANCO
        _clientes[perfil] = MongoClient(_uri(usuario, senha, auth_db), serverSelectionTimeoutMS=5000,
                                        appname=f"alerta-{perfil}")
    return _clientes[perfil][config.BANCO]


def conectar_como(usuario, senha):
    """Abre uma conexão com as credenciais de quem fez o pedido (usada pela consulta da IA)."""
    cliente = MongoClient(_uri(usuario, senha, config.BANCO), serverSelectionTimeoutMS=5000,
                          appname="alerta-consulta")
    cliente.admin.command("ping")  # já falha aqui se a senha estiver errada
    return cliente, cliente[config.BANCO]


def eh_falta_de_permissao(erro):
    """Erro 13 (Unauthorized) ou 18 (falha de autenticação) do MongoDB."""
    return isinstance(erro, OperationFailure) and erro.code in (13, 18)


def fechar_tudo():
    for cliente in _clientes.values():
        cliente.close()
    _clientes.clear()
