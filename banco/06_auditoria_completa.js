// Alerta Inteligente - Entrega 3: auditoria completa
// Rodar pelo projeto:  python cli.py banco auditoria-completa
// Recria SOMENTE a view vw_auditoria_mascarada (nenhuma coleção é apagada) para que o auditor veja,
// além de quem fez o quê, a pergunta (anonimizada), o que a IA entendeu e o que a IA respondeu.
// O IP continua mascarado. A coleção auditoria aceita os campos novos sem mudar o validador,
// porque o $jsonSchema dela não proíbe campos extras.
(function () {
  const banco = db.getSiblingDB(process.env.MONGODB_BANCO || "alerta_inteligente");
  if (banco.getCollectionNames().includes("vw_auditoria_mascarada")) banco.getCollection("vw_auditoria_mascarada").drop();
  banco.createView("vw_auditoria_mascarada", "auditoria", [
    { $project: { _id: 0, data_hora: 1, usuario: 1, acao: 1, colecao: 1, detalhe: 1, solicitante: 1, permitido: 1,
        pergunta: 1, intencao: 1, resposta_ia: 1, resposta_sha256: 1, validado: 1, origem_texto: 1,
        ip: { $concat: [{ $arrayElemAt: [{ $split: [{ $ifNull: ["$ip", "0.0.0.0"] }, "."] }, 0] }, ".***.***.***"] } } }
  ]);
  print("view recriada: vw_auditoria_mascarada (com pergunta, intencao e resposta_ia)");
  print("registros na auditoria: " + banco.auditoria.countDocuments({}));
  print("OK: auditoria completa");
})();
