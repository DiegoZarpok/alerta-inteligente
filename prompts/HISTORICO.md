# Histórico dos prompts

A versão em uso de cada prompt é definida no `.env` (`PROMPT_ALERTA_VERSAO`) e gravada em cada
alerta no MongoDB (campo `versao_prompt`), para sabermos qual versão gerou cada mensagem.

## alerta

### v1 (27/10/2026)
Versão descrita na Entrega 1: pede uma mensagem simples com nível, probabilidade, vazão e setores,
usando o contexto do RAG.

### v2 (04/11/2026, atual)
Mudanças em relação à v1 e o motivo de cada uma:

1. Separação dos blocos DADOS e CONTEXTO. Na v1 os números e os trechos dos documentos vinham
   misturados, e o modelo poderia copiar uma vazão de um documento (o boletim simulado tem 650 e
   1.240 m³/s) em vez da vazão atual.
2. Abertura obrigatória com "RISCO ALTO" ou "RISCO MÉDIO". O validador exige que o nível apareça
   no texto, e a v1 não pedia isso.
3. Proibição de outras porcentagens e vazões. O validador bloqueia qualquer número diferente do
   calculado, e a v1 não avisava isso ao modelo.
4. Limite de três orientações e de 600 caracteres, sem markdown e sem emojis, porque o texto vai
   direto para o Telegram e precisa ser lido rápido.
5. Fechamento com "Defesa Civil: 199", que o validador também exige.
6. Regra 8, para ignorar instruções dentro do CONTEXTO, como proteção contra prompt injection
   vinda de um documento da base.

A comparação entre v1 e v2 nos mesmos cenários está em `resultados/prompts/comparacao.md`
(gerado por `python cli.py avaliar-prompts`).

## risco
### v1 (04/11/2026, atual)
Resposta curta ao comando /risco, com as mesmas regras de números da v2 do alerta.

## intencao
### v1 (04/11/2026, atual)
Escolhe uma consulta pronta a partir da pergunta do operador. Não monta consulta ao banco.

## classificar_relato
### v1 (04/11/2026, atual)
Usado só para comparar o Gemini sem treino com o BERTimbau ajustado no experimento de fine-tuning.
