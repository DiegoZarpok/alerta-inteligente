// Alerta Inteligente - geração de volume para os testes de desempenho
// Padrão: 10 estações x 30 anos de leituras horárias (cerca de 2,6 milhões) e 300 mil alertas.
// Para testar rápido, defina VOLUME_ANOS=1 antes de abrir o mongosh.
// Rodar no mongosh:  load("banco/04_gerar_volume.js")

(function () {
  const banco = db.getSiblingDB("alerta_inteligente");
  const ANOS = parseInt(process.env.VOLUME_ANOS || "30", 10);
  const ESTACOES = parseInt(process.env.VOLUME_ESTACOES || "10", 10);
  const ALERTAS = parseInt(process.env.VOLUME_ALERTAS || "300000", 10);
  const SETORES = ["Setor Ribeirinho 01", "Setor Ribeirinho 02", "Setor Ribeirinho 03",
                   "Setor Ribeirinho 04", "Setor Ribeirinho 05", "Setor Ribeirinho 06"];
  const LOTE = 10000;
  const inicio = Date.UTC(2026 - ANOS, 0, 1), horas = ANOS * 365 * 24;

  banco.series_hidrologicas.deleteMany({ estacao_id: /^VOL-/ });
  banco.alertas.deleteMany({ texto: /\[VOLUME\]/ });

  let lote = [], total = 0;
  for (let e = 1; e <= ESTACOES; e++) {
    const id = "VOL-" + String(e).padStart(2, "0");
    for (let h = 0; h < horas; h++) {
      lote.push({ estacao_id: id, data_hora: new Date(inicio + h * 3600000),
                  cota_cm: null, vazao_m3s: null, chuva_mm: Math.random() < 0.05 ? Math.round(Math.random() * 200) / 10 : 0,
                  fonte: "SIMULADO" });
      if (lote.length === LOTE) { banco.series_hidrologicas.insertMany(lote, { ordered: false }); total += LOTE; lote = []; }
    }
    print(id + " concluida (" + total + " leituras ate agora)");
  }
  if (lote.length) { banco.series_hidrologicas.insertMany(lote, { ordered: false }); total += lote.length; lote = []; }

  let totalAlertas = 0;
  for (let i = 0; i < ALERTAS; i++) {
    const alto = Math.random() < 0.3;
    const qtd = 1 + Math.floor(Math.random() * 3);
    const setores = [];
    while (setores.length < qtd) { const s = SETORES[Math.floor(Math.random() * 6)]; if (!setores.includes(s)) setores.push(s); }
    lote.push({ enviado_em: new Date(inicio + Math.floor(Math.random() * horas) * 3600000),
                nivel_risco: alto ? "alto" : "medio", probabilidade: alto ? 0.75 : 0.45,
                texto: "Alerta simulado [VOLUME]", setores, qtd_destinatarios: 10 * qtd,
                modelo_llm: "gemini-2.5-flash", validado: true });
    if (lote.length === LOTE) { banco.alertas.insertMany(lote, { ordered: false }); totalAlertas += LOTE; lote = []; }
  }
  if (lote.length) { banco.alertas.insertMany(lote, { ordered: false }); totalAlertas += lote.length; }
  print("OK: " + total + " leituras e " + totalAlertas + " alertas gerados");
})();
