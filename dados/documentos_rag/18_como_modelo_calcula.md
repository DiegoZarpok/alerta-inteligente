# Como o modelo calcula o risco

> Origem: Texto próprio do grupo  
> Tipo: Próprio

Entradas (para cada dia/hora t): chuva acumulada em 24 h, 48 h e 72 h; vazão atual Q(t); variação da vazão ΔQ = Q(t) − Q(t−24h); média móvel de 7 dias da vazão; mês do ano.

Alvo: y = 1 se a vazão máxima nas 24 h seguintes for maior que 2.430 m³/s; y = 0 caso contrário.

Regressão logística: P(y=1) = 1 / (1 + e^−(β0 + β1×x1 + … + βn×xn)). Os coeficientes β são estimados por máxima verossimilhança com os dados históricos.

Random Forest: conjunto de árvores de decisão; a probabilidade é a média dos votos das árvores.

A avaliação usa divisão temporal (treina no passado, testa nos anos mais recentes) para simular uma previsão real.
