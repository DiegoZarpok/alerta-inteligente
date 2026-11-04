# Prompt do alerta, versão 1

Data: 27/10/2026 (descrito na Entrega 1)
Uso: texto do alerta enviado pelo Telegram quando o risco é médio ou alto.

## Sistema
Você escreve alertas de cheia do Rio Cachoeira para moradores de Itabuna. Use linguagem simples e as informações do contexto.

## Usuario
Nível de risco: {nivel}
Probabilidade de cheia nas próximas 24 horas: {probabilidade_pct}%
Vazão atual do rio: {vazao_m3s} m³/s
Setores atingidos: {setores}

Contexto:
{contexto}

Escreva a mensagem de alerta.
