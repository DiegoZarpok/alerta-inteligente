# Limiar de transbordamento do Rio Cachoeira

> Origem: Resumo próprio de artigo público (Farias & Gomes, Rev. Bras. Geografia Física, 2023)  
> Tipo: Real (público)

Um estudo da UESC (2023) comparou as séries de vazão do Rio Cachoeira com os anos em que Itabuna teve inundações. Os picos de vazão máxima coincidiram com esses anos. O estudo indicou que, a partir de uma vazão de aproximadamente 2.430 m³/s, a água extravasa o leito do rio.

O Alerta Inteligente usa esse valor como limiar de cheia (Q_limite = 2.430 m³/s). O modelo estima a probabilidade de a vazão ultrapassar esse limiar nas próximas 24 horas.

Como cheias desse porte são raras, o projeto também testa um limiar mais baixo de "atenção" (definido pelo grupo a partir do percentil 99 da série histórica). Assim existem mais exemplos positivos para treinar o modelo.
