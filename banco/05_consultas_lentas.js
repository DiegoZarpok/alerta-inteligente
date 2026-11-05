// Alerta Inteligente - as duas consultas lentas, medidas antes e depois dos índices
// Rodar pelo projeto, depois do script 04:  python cli.py banco consultas-lentas
// Os planos de execução completos ficam em resultados/banco/ (um arquivo JSON por consulta).

(function () {
  const fs = require("fs");
  const path = require("path");
  const banco = db.getSiblingDB(process.env.MONGODB_BANCO || "alerta_inteligente");
  const pasta = path.join(process.cwd(), "resultados", "banco");
  fs.mkdirSync(pasta, { recursive: true });
  const linhas = [];

  function acharStats(plano) {
    if (!plano || typeof plano !== "object") return null;
    if (plano.executionStats) return plano.executionStats;
    for (const v of Object.values(plano)) { const r = acharStats(v); if (r) return r; }
    return null;
  }
  function estagios(plano) {
    const nomes = [];
    (function andar(no) {
      if (!no || typeof no !== "object") return;
      if (typeof no.stage === "string") nomes.push(no.stage);
      Object.values(no).forEach(andar);
    })(plano.queryPlanner ? plano.queryPlanner.winningPlan : plano);
    return [...new Set(nomes)].join(" > ");
  }
  function medir(nome, arquivo, explicar) {
    const plano = explicar();
    fs.writeFileSync(path.join(pasta, arquivo), JSON.stringify(plano, null, 2));
    const st = acharStats(plano) || {};
    const texto = JSON.stringify(plano);
    const tipo = texto.includes("IXSCAN") ? "IXSCAN (usa índice)" : texto.includes("COLLSCAN") ? "COLLSCAN (lê a coleção toda)" : "?";
    const linha = nome + " | tempo: " + st.executionTimeMillis + " ms | documentos lidos: " + st.totalDocsExamined +
                  " | chaves de índice lidas: " + st.totalKeysExamined + " | " + tipo + " | estágios: " + estagios(plano);
    print(linha);
    linhas.push(linha);
  }

  const total = banco.series_hidrologicas.estimatedDocumentCount();
  const totalAlertas = banco.alertas.estimatedDocumentCount();
  print("series_hidrologicas: " + total + " documentos | alertas: " + totalAlertas + " documentos");
  linhas.push("series_hidrologicas: " + total + " documentos | alertas: " + totalAlertas + " documentos");

  // Consulta 1: chuva acumulada nas últimas 72 h de uma estação (usada a cada previsão)
  const fim = banco.series_hidrologicas.find({ estacao_id: "VOL-05" }).sort({ data_hora: -1 }).limit(1).toArray()[0];
  if (!fim) { print("Rode antes: python cli.py banco volume"); return; }
  const fimData = fim.data_hora, iniData = new Date(fimData.getTime() - 72 * 3600000);
  const consulta1 = () => banco.series_hidrologicas.explain("executionStats").aggregate([
    { $match: { estacao_id: "VOL-05", data_hora: { $gte: iniData, $lte: fimData } } },
    { $group: { _id: "$estacao_id", chuva_72h: { $sum: "$chuva_mm" } } }
  ]);

  // Consulta 2: últimos alertas de um setor num período (usada pelo operador e pelo /risco)
  const consulta2 = () => banco.alertas.find({
    setores: "Setor Ribeirinho 03",
    enviado_em: { $gte: new Date(Date.UTC(2015, 0, 1)), $lt: new Date(Date.UTC(2016, 0, 1)) }
  }).sort({ enviado_em: -1 }).limit(50).explain("executionStats");

  try { banco.series_hidrologicas.dropIndex("idx_estacao_data"); } catch (e) {}
  try { banco.alertas.dropIndex("idx_setor_data"); } catch (e) {}

  // O índice geral { enviado_em: -1 } (criado no script 01 para listar os últimos alertas)
  // fica escondido durante a medição "antes", para medir a consulta sem nenhum índice que a ajude.
  // Ele volta a valer logo depois (unhideIndex), sem precisar ser recriado.
  const escondidos = [];
  banco.alertas.getIndexes().forEach(function (ix) {
    if (ix.name === "_id_") return;
    try { banco.alertas.hideIndex(ix.name); escondidos.push(ix.name); } catch (e) {}
  });
  if (escondidos.length) {
    const aviso = "(índices gerais de alertas escondidos durante a medição antes: " + escondidos.join(", ") + ")";
    print(aviso); linhas.push(aviso);
  }

  print("--- ANTES dos índices ---"); linhas.push("--- ANTES dos índices ---");
  try {
    medir("Consulta 1 (chuva 72 h)", "consulta1_antes.json", consulta1);
    medir("Consulta 2 (alertas por setor)", "consulta2_antes.json", consulta2);
  } finally {
    escondidos.forEach(function (nome) { banco.alertas.unhideIndex(nome); });
  }

  banco.series_hidrologicas.createIndex({ estacao_id: 1, data_hora: -1 }, { name: "idx_estacao_data" });
  banco.alertas.createIndex({ setores: 1, enviado_em: -1 }, { name: "idx_setor_data" });

  print("--- DEPOIS dos índices ---"); linhas.push("--- DEPOIS dos índices ---");
  medir("Consulta 1 (chuva 72 h)", "consulta1_depois.json", consulta1);
  medir("Consulta 2 (alertas por setor)", "consulta2_depois.json", consulta2);

  fs.writeFileSync(path.join(pasta, "consultas_lentas.txt"), linhas.join("\n") + "\n");
  print("Planos de execução salvos em " + pasta);
})();
