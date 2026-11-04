# Níveis de risco do Alerta Inteligente

> Origem: Definição do projeto (grupo)  
> Tipo: Próprio  
> Nível: todos

O modelo calcula P, a probabilidade de a vazão na estação Contorno da BR-101 passar de cerca de 930 m³/s (cheia de 3 anos de retorno) no dia seguinte. O nível de risco é definido assim:

- Baixo: P menor que 0,30. Situação normal. Nenhum alerta é enviado; a leitura é apenas registrada.
- Médio: P entre 0,30 e 0,60. Atenção. Alerta preventivo e monitoramento a cada 15 minutos.
- Alto: P a partir de 0,60. Alerta de cheia provável, com orientações de proteção.

Os cortes podem ser ajustados depois da avaliação para priorizar o recall, ou seja, para que o sistema perca o menor número possível de cheias reais, aceitando alguns alarmes falsos.

O nível é sempre decidido pelo modelo matemático. O modelo de linguagem apenas redige a mensagem.
