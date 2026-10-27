// Alerta Inteligente - as duas consultas lentas, medidas antes e depois dos índices
// Rodar no mongosh depois do script 04:  load("banco/05_consultas_lentas.js")

(function () {
  const banco = db.getSiblingDB("alerta_inteligente");

  function acharStats(plano) {
    if (!plano || typeof plano !== "object") return null;
    if (plano.executionStats) return plano.executionStats;
    for (const v of Object.values(plano)) { const r = acharStats(v); if (r) return r; }
    return null;
  }
  function medir(nome, explicar) {
    const plano = explicar();
    const st = acharStats(plano) || {};
    const texto = JSON.stringify(plano);
    const estagio = texto.includes("IXSCAN") ? "IXSCAN (usa indice)" : texto.includes("COLLSCAN") ? "COLLSCAN (le a colecao toda)" : "?";
    print(nome + " | tempo: " + st.executionTimeMillis + " ms | documentos lidos: " + st.totalDocsExamined + " | " + estagio);
  }

  // Consulta 1: chuva acumulada nas últimas 72 h de uma estação (usada a cada previsão)
  const fim = banco.series_hidrologicas.find({ estacao_id: "VOL-05" }).sort({ data_hora: -1 }).limit(1).toArray()[0];
  if (!fim) { print("Rode antes o script 04_gerar_volume.js"); return; }
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

  ["idx_estacao_data"].forEach(n => { try { banco.series_hidrologicas.dropIndex(n); } catch (e) {} });
  ["idx_setor_data"].forEach(n => { try { banco.alertas.dropIndex(n); } catch (e) {} });

  print("--- ANTES dos indices ---");
  medir("Consulta 1 (chuva 72 h)", consulta1);
  medir("Consulta 2 (alertas por setor)", consulta2);

  banco.series_hidrologicas.createIndex({ estacao_id: 1, data_hora: -1 }, { name: "idx_estacao_data" });
  banco.alertas.createIndex({ setores: 1, enviado_em: -1 }, { name: "idx_setor_data" });

  print("--- DEPOIS dos indices ---");
  medir("Consulta 1 (chuva 72 h)", consulta1);
  medir("Consulta 2 (alertas por setor)", consulta2);
})();
