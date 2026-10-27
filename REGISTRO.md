# Histórico do projeto Alerta Inteligente

## Proposta (14/10/2026)
- Grupo: Sentinela do Cachoeira
- Componentes: Diego Ailton Silva Barbosa, Pedro Henrique Costa, Alexandre Pereira Muniz e Marcos Vinicius Farias Silva
- Título: Alerta Inteligente: IA para Previsão de Cheias do Rio Cachoeira em Itabuna
- Problema: cheias do Rio Cachoeira em Itabuna (registros desde 1914; em dezembro de 2021 o rio subiu cerca de 9 m).
- Dados: vazão e cota da ANA (Hidroweb, estação Ferradas 53170000, com registros desde a década de 1960), chuva do INMET e do CEMADEN.
- Referência para o limiar de cheia: transbordamento a partir de cerca de 2.430 m³/s (Farias e Gomes, UESC, 2023).
- Integração com SIS913 - Bancos de Dados NoSQL, usando MongoDB.

## Entrega 1: Arquitetura (27/10/2026)
- Coleta pelo n8n a cada 1 hora (a cada 15 minutos quando o risco for médio ou alto).
- Modelo de previsão: Regressão Logística e Random Forest. Calcula P(vazão > 2.430 m³/s nas próximas 24 h). Risco baixo abaixo de 0,30, médio entre 0,30 e 0,60, alto a partir de 0,60.
- LLM: Gemini 2.5 Flash, usado só para escrever o alerta. Reserva: Flash-Lite. Custo estimado de US$ 1,50 (cerca de R$ 7,80) a cada 1.000 usos.
- RAG: 24 documentos, divididos por seção (até 400 tokens, sobreposição de 50), embeddings locais com paraphrase-multilingual-MiniLM-L12-v2, busca vetorial no MongoDB Atlas (4 trechos mais parecidos, filtrados pelo nível de risco).
- Validador: impede o envio de mensagem com números diferentes dos calculados.
- Fine-tuning: BERTimbau-base classificando relatos de moradores em confirmado, observação ou não relacionado; 300 relatos fictícios; comparação com o Gemini sem treino pelo F1-macro.
- Interface: bot do Telegram com comandos fixos (/risco, /setor, /relato, /sair) e terminal do operador.
- Coleções no MongoDB: series_hidrologicas, previsoes, alertas, estacoes, documentos, moradores, relatos, auditoria (mais 3 views mascaradas).
- Maior risco: poucos eventos de cheia na série e falhas nas estações.
- Documento da Entrega 1 em formato de trabalho acadêmico (capa, sumário, texto corrido, figuras em páginas próprias e referências).
- Plano de 3 semanas: (1) dados no MongoDB e análise exploratória; (2) modelos treinados e avaliados, RAG montado; (3) fluxo completo no n8n e testes de alucinação, fora do escopo e prompt injection.

## Entrega 1: Segurança e integração (27/10/2026)
- O grupo cursa também Bancos de Dados NoSQL, então a Entrega 1 inclui a Parte de Segurança e a Parte de integração.
- Modelo de dados com 8 coleções e campos classificados em público, interno e sensível.
- Proteção dos sensíveis: hash SHA-256 com sal (chat_hash), criptografia AES-256-GCM (chat_cifrado e texto_cifrado), mascaramento (apelido e IP) e views mascaradas no lugar de RLS.
- 7 papéis com privilégio mínimo; o serviço de IA não lê moradores nem relatos; auditoria só aceita insert.
- Ameaças: injeção NoSQL pelo bot e escalonamento de privilégio. Gargalo: consultas nas séries sem índice.
- Consultas lentas: chuva acumulada em 72 h (índice {estacao_id, data_hora}) e alertas por setor e período (índice {setores, enviado_em}).
- Scripts em banco/: 01 criação, 02 carga inicial (70.080 leituras simuladas, 24 documentos, 50 moradores e 30 relatos fictícios), 03 papéis e usuários, 04 volume (cerca de 2,6 milhões de leituras e 300 mil alertas), 05 medição antes e depois dos índices.
- Ataques que serão testados: prompt injection, injeção NoSQL e escalonamento de privilégio.

## Próximos passos
- Apresentação parcial de 5 minutos.
- Baixar as séries da ANA (Ferradas) e do INMET e carregar no MongoDB.
