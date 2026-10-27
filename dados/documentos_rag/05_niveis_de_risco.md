# Níveis de risco do Alerta Inteligente

> Origem: Definição do projeto (grupo)  
> Tipo: Próprio

O modelo calcula P, a probabilidade de a vazão em Ferradas passar de 2.430 m³/s nas próximas 24 horas. O nível de risco é definido assim:

- Baixo: P < 0,30. Situação normal. Nenhum alerta é enviado; a leitura é apenas registrada.
- Médio: 0,30 ≤ P < 0,60. Atenção. Alerta preventivo e monitoramento a cada 15 minutos.
- Alto: P ≥ 0,60. Alerta de cheia provável, com orientações de proteção.

Os cortes (0,30 e 0,60) serão ajustados na etapa de avaliação para priorizar o recall, ou seja, para que o sistema perca o menor número possível de cheias reais, aceitando alguns alarmes falsos.

O nível é sempre decidido pelo modelo matemático. O LLM apenas redige a mensagem.
