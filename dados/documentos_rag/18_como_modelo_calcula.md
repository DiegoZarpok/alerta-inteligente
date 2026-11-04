# Como o modelo calcula o risco

> Origem: Texto próprio do grupo  
> Tipo: Próprio  
> Nível: todos

Entradas de cada dia t: chuva média da bacia acumulada em 24, 48 e 72 horas; vazão atual na estação Contorno da BR-101; variação da vazão em relação ao dia anterior; média móvel de 7 dias da vazão; vazão e variação em Ferradas, rio acima; e o mês do ano. Vazões e chuvas entram em escala logarítmica, porque variam de poucos m³/s a mais de 2.000 m³/s.

Alvo: y = 1 se a vazão média do dia seguinte passar de cerca de 930 m³/s (cheia de 3 anos de retorno, pela curva do estudo da UESC); y = 0 caso contrário.

Regressão logística: P(y=1) = 1 / (1 + e^−(β0 + β1×x1 + … + βn×xn)). Os coeficientes β são estimados por máxima verossimilhança com os dados históricos.

Random Forest: conjunto de árvores de decisão; a probabilidade é a média dos votos das árvores.

A avaliação usa divisão temporal: treina com os anos antes de 2000 e testa nos anos seguintes, que o modelo nunca viu. O resultado é comparado com a regra "amanhã igual a hoje".
