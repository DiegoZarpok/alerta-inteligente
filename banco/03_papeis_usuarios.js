// Alerta Inteligente - papéis e usuários (privilégio mínimo)
// Rodar no mongosh conectado como administrador:  load("banco/03_papeis_usuarios.js")
// As senhas são digitadas na hora (passwordPrompt) e não ficam salvas em nenhum arquivo.
// O MongoDB nega tudo que não foi concedido: os "NEGADO" da matriz são as permissões que ficam de fora.

(function () {
  const banco = db.getSiblingDB("alerta_inteligente");
  const NOME_BANCO = "alerta_inteligente";
  const p = (colecao, acoes) => ({ resource: { db: NOME_BANCO, collection: colecao }, actions: acoes });
  const auditar = p("auditoria", ["insert"]); // todos registram, ninguém altera ou apaga

  const papeis = {
    papel_coleta:        [p("series_hidrologicas", ["insert"]), p("estacoes", ["find"]), auditar],
    papel_modelo:        [p("series_hidrologicas", ["find"]), p("estacoes", ["find"]), p("previsoes", ["insert", "find"]), auditar],
    papel_ia:            [p("documentos", ["find"]), p("previsoes", ["find"]), p("alertas", ["insert"]), auditar],
    papel_classificador: [p("vw_relatos_anonimizados", ["find"]), p("relatos", ["update"]), auditar],
    papel_bot:           [p("moradores", ["find", "insert", "update", "remove"]), p("relatos", ["insert"]), p("alertas", ["find"]), auditar],
    papel_operador:      [p("series_hidrologicas", ["find"]), p("estacoes", ["find"]), p("previsoes", ["find"]), p("alertas", ["find"]),
                          p("vw_moradores_mascarado", ["find"]), p("vw_relatos_anonimizados", ["find"])],
    papel_auditor:       [p("vw_auditoria_mascarada", ["find"]), p("alertas", ["find"])]
  };

  Object.entries(papeis).forEach(([papel, privilegios]) => {
    if (banco.getRole(papel)) banco.dropRole(papel);
    banco.createRole({ role: papel, privileges: privilegios, roles: [] });
    print("papel criado: " + papel);
  });

  const usuarios = {
    svc_coleta: "papel_coleta", svc_modelo: "papel_modelo", svc_ia: "papel_ia",
    svc_classificador: "papel_classificador", svc_bot: "papel_bot",
    operador_defesa_civil: "papel_operador", auditor: "papel_auditor"
  };
  Object.entries(usuarios).forEach(([usuario, papel]) => {
    if (banco.getUser(usuario)) banco.dropUser(usuario);
    print("Senha para " + usuario + ":");
    banco.createUser({ user: usuario, pwd: passwordPrompt(), roles: [{ role: papel, db: NOME_BANCO }] });
    print("usuario criado: " + usuario + " (" + papel + ")");
  });
  print("OK: papeis e usuarios criados");
})();
