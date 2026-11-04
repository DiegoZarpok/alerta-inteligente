"""Para os testes automáticos: simula papéis, views e validação de esquema do MongoDB.

O servidor usado nos testes (compatível com MongoDB) não tem createRole, views nem $jsonSchema.
Este simulador aplica, por cima dele, a mesma matriz de permissões da Entrega 1, as views do script
01 e os validadores $jsonSchema extraídos do próprio banco/01_criar_banco.js.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

from bson import ObjectId
from pymongo.errors import OperationFailure

from src.permissoes import ESPERADO

RAIZ = Path(__file__).resolve().parents[1]

VIEWS = {
    "vw_relatos_anonimizados": ("relatos", {"_id": 1, "recebido_em": 1, "setor": 1, "texto_anonimizado": 1, "classe": 1}),
    "vw_moradores_mascarado": ("moradores", {"_id": 0, "setor": 1, "ativo": 1, "inscrito_em": 1}),
    "vw_auditoria_mascarada": ("auditoria", {"_id": 0, "data_hora": 1, "usuario": 1, "acao": 1, "colecao": 1,
                                             "detalhe": 1, "solicitante": 1, "permitido": 1, "ip": 1}),
}
ACAO = {"find": "find", "find_one": "find", "distinct": "find", "count_documents": "find", "aggregate": "find",
        "estimated_document_count": "find", "insert_one": "insert", "insert_many": "insert",
        "update_one": "update", "update_many": "update", "delete_one": "remove", "delete_many": "remove"}

_EXTRATOR = r"""
const fs = require('fs'); const esquemas = {};
const banco = { getCollectionNames: () => [], getCollection: () => ({ drop() {} }),
  createCollection: (n, o) => { esquemas[n] = o.validator.$jsonSchema; },
  createView() {}, moradores: { createIndex() {} }, relatos: { createIndex() {} }, previsoes: { createIndex() {} },
  alertas: { createIndex() {} }, auditoria: { createIndex() {} }, documentos: { createIndex() {} } };
global.db = { getSiblingDB: () => banco }; global.print = () => {};
eval(fs.readFileSync(process.argv[1], 'utf8'));
process.stdout.write(JSON.stringify(esquemas));
"""


def extrair_esquemas():
    r = subprocess.run(["node", "-e", _EXTRATOR, str(RAIZ / "banco" / "01_criar_banco.js")],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _tipo(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int" if -2**31 <= v < 2**31 else "long"
    if isinstance(v, float):
        return "double"
    if isinstance(v, str):
        return "string"
    if isinstance(v, datetime):
        return "date"
    if isinstance(v, (list, tuple)):
        return "array"
    if isinstance(v, dict):
        return "object"
    if isinstance(v, ObjectId):
        return "objectId"
    return type(v).__name__


def validar(doc, esquema, caminho="doc"):
    import re
    t = _tipo(doc)
    if "bsonType" in esquema:
        permitidos = esquema["bsonType"] if isinstance(esquema["bsonType"], list) else [esquema["bsonType"]]
        if t not in permitidos:
            raise OperationFailure(f"Document failed validation: {caminho} é {t}, esperado {permitidos}", code=121)
    if "enum" in esquema and doc not in esquema["enum"]:
        raise OperationFailure(f"Document failed validation: {caminho}={doc!r} fora do enum", code=121)
    if isinstance(doc, (int, float)) and not isinstance(doc, bool):
        if "minimum" in esquema and doc < esquema["minimum"]:
            raise OperationFailure(f"Document failed validation: {caminho} abaixo do mínimo", code=121)
        if "maximum" in esquema and doc > esquema["maximum"]:
            raise OperationFailure(f"Document failed validation: {caminho} acima do máximo", code=121)
    if isinstance(doc, str):
        if "pattern" in esquema and not re.search(esquema["pattern"], doc):
            raise OperationFailure(f"Document failed validation: {caminho} não bate com o padrão", code=121)
        if len(doc) < esquema.get("minLength", 0) or len(doc) > esquema.get("maxLength", 10**9):
            raise OperationFailure(f"Document failed validation: tamanho de {caminho}", code=121)
    if isinstance(doc, dict):
        for r in esquema.get("required", []):
            if r not in doc:
                raise OperationFailure(f"Document failed validation: falta {caminho}.{r}", code=121)
        for k, sub in esquema.get("properties", {}).items():
            if k in doc:
                validar(doc[k], sub, f"{caminho}.{k}")
    if isinstance(doc, (list, tuple)) and "items" in esquema:
        for i, x in enumerate(doc):
            validar(x, esquema["items"], f"{caminho}[{i}]")


def _mascarar_ip(doc):
    """O mesmo cálculo da view vw_auditoria_mascarada: mantém só o primeiro bloco do IP."""
    if "ip" in doc:
        doc["ip"] = str(doc.get("ip") or "0.0.0.0").split(".")[0] + ".***.***.***"
    return doc


CALCULOS = {"vw_auditoria_mascarada": _mascarar_ip}


class CursorDaView:
    """Cursor que aplica os campos calculados da view (o servidor de testes não tem views)."""

    def __init__(self, cursor, calculo):
        self._c, self._calc = cursor, calculo

    def sort(self, *a, **k):
        self._c = self._c.sort(*a, **k)
        return self

    def limit(self, n):
        self._c = self._c.limit(n)
        return self

    def __iter__(self):
        return (self._calc(d) for d in self._c)


class Colecao:
    def __init__(self, banco, nome):
        self._b, self._nome = banco, nome
        self._real = banco.raw[VIEWS[nome][0] if nome in VIEWS else nome]

    def _checar(self, acao):
        if self._b.perfil == "admin":
            return
        if not ESPERADO.get(self._b.perfil, {}).get((self._nome, acao), False):
            raise OperationFailure(f"not authorized on {self._b.raw.name} to execute command {acao} on {self._nome}",
                                   code=13)

    def _validar_por_id(self, filtro):
        esquema = self._b.esquemas.get(self._nome)
        if esquema:
            for d in self._real.find(filtro):
                d.pop("_id", None) if self._nome != "estacoes" else None
                validar(d, esquema)

    def __getattr__(self, metodo):
        if metodo not in ACAO:
            raise AttributeError(metodo)
        acao = ACAO[metodo]

        def chamada(*args, **kwargs):
            self._checar(acao)
            if kwargs.get("upsert"):
                self._checar("insert")
            if self._nome in VIEWS:
                if acao != "find":
                    raise OperationFailure("Namespace is a view, not a collection", code=166)
                proj = VIEWS[self._nome][1]
                if metodo in ("find", "find_one"):
                    filtro = args[0] if args else kwargs.pop("filter", {})
                    campos = args[1] if len(args) > 1 else kwargs.pop("projection", None)
                    final = dict(proj)
                    if campos:
                        final = {k: v for k, v in campos.items() if k == "_id" or k in proj} or proj
                        if "_id" not in campos and proj.get("_id") == 0:
                            final["_id"] = 0
                    if self._nome in CALCULOS and (not campos or "ip" in campos):
                        final["ip"] = 1
                    resultado = getattr(self._real, metodo)(filtro, final, **kwargs)
                    if metodo == "find_one":
                        return CALCULOS.get(self._nome, lambda d: d)(resultado) if resultado else resultado
                    return CursorDaView(resultado, CALCULOS.get(self._nome, lambda d: d))
                return getattr(self._real, metodo)(*args, **kwargs)
            esquema = self._b.esquemas.get(self._nome)
            if acao == "insert" and esquema:
                docs = args[0] if metodo == "insert_many" else [args[0]]
                for d in docs:
                    validar({k: v for k, v in d.items() if k != "_id" or self._nome == "estacoes"}, esquema)
            resultado = getattr(self._real, metodo)(*args, **kwargs)
            if acao == "update" and esquema:
                self._validar_por_id(args[0])
            return resultado
        return chamada


class Banco:
    """Banco 'logado' com um perfil. raw é o banco de verdade (sem permissões)."""

    def __init__(self, raw, perfil, esquemas):
        self.raw, self.perfil, self.esquemas = raw, perfil, esquemas
        self.name = raw.name

    def __getitem__(self, nome):
        return Colecao(self, nome)

    def __getattr__(self, nome):
        if nome.startswith("_"):
            raise AttributeError(nome)
        return Colecao(self, nome)

    def command(self, nome, *args, **kwargs):
        if self.perfil != "admin":
            raise OperationFailure(f"not authorized on {self.raw.name} to execute command {{ {nome} }}", code=13)
        return {"ok": 1}
