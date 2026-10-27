// Alerta Inteligente - criação do banco
// Rodar no mongosh, de dentro da pasta do projeto:  load("banco/01_criar_banco.js")

(function () {

  const banco = db.getSiblingDB("alerta_inteligente");

  function recriar(nome, validador) {
    if (banco.getCollectionNames().includes(nome)) banco.getCollection(nome).drop();
    banco.createCollection(nome, { validator: { $jsonSchema: validador }, validationLevel: "strict" });
    print("colecao criada: " + nome);
  }

  // séries de rio e chuva (dados públicos)
  recriar("series_hidrologicas", {
    bsonType: "object",
    required: ["estacao_id", "data_hora", "fonte"],
    properties: {
      estacao_id: { bsonType: "string" },
      data_hora: { bsonType: "date" },
      cota_cm: { bsonType: ["double", "int", "null"] },
      vazao_m3s: { bsonType: ["double", "int", "null"], minimum: 0 },
      chuva_mm: { bsonType: ["double", "int", "null"], minimum: 0 },
      fonte: { enum: ["ANA", "INMET", "CEMADEN", "SIMULADO"] }
    }
  });

  recriar("estacoes", {
    bsonType: "object",
    required: ["_id", "nome", "tipo"],
    properties: {
      _id: { bsonType: "string" },
      nome: { bsonType: "string" },
      tipo: { enum: ["fluviometrica", "pluviometrica"] },
      latitude: { bsonType: ["double", "null"] },
      longitude: { bsonType: ["double", "null"] }
    }
  });

  recriar("previsoes", {
    bsonType: "object",
    required: ["data_hora", "probabilidade", "nivel_risco", "versao_modelo"],
    properties: {
      data_hora: { bsonType: "date" },
      probabilidade: { bsonType: ["double", "int"], minimum: 0, maximum: 1 },
      nivel_risco: { enum: ["baixo", "medio", "alto"] },
      versao_modelo: { bsonType: "string" },
      variaveis: { bsonType: "object" }
    }
  });

  recriar("alertas", {
    bsonType: "object",
    required: ["enviado_em", "nivel_risco", "texto", "setores"],
    properties: {
      enviado_em: { bsonType: "date" },
      nivel_risco: { enum: ["medio", "alto"] },
      probabilidade: { bsonType: ["double", "int"] },
      texto: { bsonType: "string" },
      setores: { bsonType: "array", items: { bsonType: "string" } },
      qtd_destinatarios: { bsonType: "int" },
      modelo_llm: { bsonType: "string" },
      validado: { bsonType: "bool" }
    }
  });

  recriar("documentos", {
    bsonType: "object",
    required: ["arquivo", "titulo", "conteudo", "tipo"],
    properties: {
      arquivo: { bsonType: "string" },
      titulo: { bsonType: "string" },
      conteudo: { bsonType: "string" },
      tipo: { enum: ["Real (público)", "Próprio", "Fictício"] },
      embedding: { bsonType: ["array", "null"] }
    }
  });

  // moradores inscritos no bot: nunca guarda o id do Telegram em texto puro
  recriar("moradores", {
    bsonType: "object",
    required: ["chat_hash", "chat_cifrado", "setor", "inscrito_em"],
    properties: {
      chat_hash: { bsonType: "string", minLength: 64, maxLength: 64 },
      chat_cifrado: { bsonType: "string" },
      apelido_mascarado: { bsonType: "string" },
      setor: { bsonType: "string", pattern: "^Setor Ribeirinho 0[1-6]$" },
      inscrito_em: { bsonType: "date" },
      ativo: { bsonType: "bool" }
    }
  });

  recriar("relatos", {
    bsonType: "object",
    required: ["morador_hash", "recebido_em", "texto_anonimizado", "texto_cifrado"],
    properties: {
      morador_hash: { bsonType: "string", minLength: 64, maxLength: 64 },
      recebido_em: { bsonType: "date" },
      setor: { bsonType: "string" },
      texto_anonimizado: { bsonType: "string" },
      texto_cifrado: { bsonType: "string" },
      classe: { enum: ["confirmado", "observacao", "nao_relacionado", null] }
    }
  });

  recriar("auditoria", {
    bsonType: "object",
    required: ["data_hora", "usuario", "acao", "colecao"],
    properties: {
      data_hora: { bsonType: "date" },
      usuario: { bsonType: "string" },
      acao: { bsonType: "string" },
      colecao: { bsonType: "string" },
      ip: { bsonType: "string" },
      detalhe: { bsonType: "string" }
    }
  });

  // índices básicos (os das consultas lentas ficam para o script 05, para medir antes e depois)
  banco.moradores.createIndex({ chat_hash: 1 }, { unique: true });
  banco.moradores.createIndex({ setor: 1, ativo: 1 });
  banco.relatos.createIndex({ recebido_em: -1 });
  banco.previsoes.createIndex({ data_hora: -1 });
  banco.auditoria.createIndex({ data_hora: -1 });
  banco.documentos.createIndex({ arquivo: 1 }, { unique: true });

  // views com campos mascarados (é por elas que operador e auditor leem)
  ["vw_moradores_mascarado", "vw_relatos_anonimizados", "vw_auditoria_mascarada"].forEach(v => {
    if (banco.getCollectionNames().includes(v)) banco.getCollection(v).drop();
  });
  banco.createView("vw_moradores_mascarado", "moradores", [
    { $project: { _id: 0, setor: 1, ativo: 1, inscrito_em: 1,
        morador: { $concat: [{ $substrCP: ["$chat_hash", 0, 8] }, "..."] } } }
  ]);
  banco.createView("vw_relatos_anonimizados", "relatos", [
    { $project: { _id: 1, recebido_em: 1, setor: 1, texto_anonimizado: 1, classe: 1 } }
  ]);
  banco.createView("vw_auditoria_mascarada", "auditoria", [
    { $project: { _id: 0, data_hora: 1, usuario: 1, acao: 1, colecao: 1, detalhe: 1,
        ip: { $concat: [{ $arrayElemAt: [{ $split: ["$ip", "."] }, 0] }, ".***.***.***"] } } }
  ]);
  print("views criadas: vw_moradores_mascarado, vw_relatos_anonimizados, vw_auditoria_mascarada");
  print("OK: banco alerta_inteligente criado");
})();
