// Alerta Inteligente - papéis e usuários (privilégio mínimo)
// Rodar pelo projeto:  python cli.py banco papeis
// As senhas vêm do .env (SENHA_SVC_COLETA, ...). Se alguma faltar, o mongosh pede para digitar.
//
// GRANT: cada papel recebe só as ações listadas abaixo.
// DENY: o MongoDB nega tudo o que não foi concedido. Os pontos de negação planejados na Entrega 1
// são as permissões deixadas de fora de propósito:
//   - papel_ia NÃO lê moradores, relatos nem auditoria
//   - papel_operador NÃO lê as coleções moradores e relatos (só as views mascaradas)
//   - nenhum papel altera ou apaga a auditoria, cria usuários ou concede papéis

(function () {
  const banco = db.getSiblingDB(process.env.MONGODB_BANCO || "alerta_inteligente");
  const NOME_BANCO = process.env.MONGODB_BANCO || "alerta_inteligente";
  const p = (colecao, acoes) => ({ resource: { db: NOME_BANCO, collection: colecao }, actions: acoes });
  const auditar = p("auditoria", ["insert"]);

  const papeis = {
    papel_coleta:        [p("series_hidrologicas", ["find", "insert"]), p("estacoes", ["find"]), auditar],
    papel_modelo:        [p("series_hidrologicas", ["find"]), p("estacoes", ["find"]), p("previsoes", ["insert", "find"]), auditar],
    papel_ia:            [p("documentos", ["find"]), p("previsoes", ["find"]), p("alertas", ["insert"]), auditar],
    papel_classificador: [p("vw_relatos_anonimizados", ["find"]), p("relatos", ["update"]), auditar],
    papel_bot:           [p("moradores", ["find", "insert", "update", "remove"]), p("relatos", ["insert", "remove"]),
                          p("alertas", ["find"]), auditar],
    papel_n8n:           [auditar],
    papel_operador:      [p("series_hidrologicas", ["find"]), p("estacoes", ["find"]), p("previsoes", ["find"]),
                          p("alertas", ["find"]), p("vw_moradores_mascarado", ["find"]), p("vw_relatos_anonimizados", ["find"])],
    papel_auditor:       [p("vw_auditoria_mascarada", ["find"]), p("alertas", ["find"])]
  };

  Object.entries(papeis).forEach(([papel, privilegios]) => {
    if (banco.getRole(papel)) banco.dropRole(papel);
    banco.createRole({ role: papel, privileges: privilegios, roles: [] });
    print("papel criado: " + papel);
  });

  const usuarios = {
    svc_coleta: ["papel_coleta", "SENHA_SVC_COLETA"],
    svc_modelo: ["papel_modelo", "SENHA_SVC_MODELO"],
    svc_ia: ["papel_ia", "SENHA_SVC_IA"],
    svc_classificador: ["papel_classificador", "SENHA_SVC_CLASSIFICADOR"],
    svc_bot: ["papel_bot", "SENHA_SVC_BOT"],
    svc_n8n: ["papel_n8n", "SENHA_SVC_N8N"],
    operador_defesa_civil: ["papel_operador", "SENHA_OPERADOR"],
    auditor: ["papel_auditor", "SENHA_AUDITOR"]
  };
  Object.entries(usuarios).forEach(([usuario, [papel, variavel]]) => {
    if (banco.getUser(usuario)) banco.dropUser(usuario);
    let senha = process.env[variavel];
    if (!senha) {
      print("Senha para " + usuario + ":");
      senha = passwordPrompt();
    }
    banco.createUser({ user: usuario, pwd: senha, roles: [{ role: papel, db: NOME_BANCO }] });
    print("usuario criado: " + usuario + " (" + papel + ")");
  });
  print("OK: papeis e usuarios criados");
})();
