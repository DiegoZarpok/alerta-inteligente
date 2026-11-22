# Alerta Inteligente: Previsão de Cheias do Rio Cachoeira (Itabuna-BA)

Grupo Sentinela do Cachoeira. SIS939 Projeto de Inteligência Artificial, integrado com SIS913 Bancos de Dados NoSQL (Segurança e Otimização). Unex Itabuna, 2026.

Componentes: Diego Ailton Silva Barbosa (241071014), Pedro Henrique Costa (241071196), Alexandre Pereira Muniz (242070491) e Marcos Vinicius Farias Silva (241070792).

Versão final (Entrega 3, 01/12/2026). Ferramenta experimental de estimativa de risco: não substitui a Defesa Civil (199).

## 1. O problema

Itabuna sofre com as cheias do Rio Cachoeira desde pelo menos 1914; em dezembro de 2021 o rio subiu cerca de 9 metros e desalojou milhares de pessoas. O aviso costuma chegar quando a água já está na rua. O projeto responde a uma pergunta concreta: **qual é a probabilidade de a vazão do rio passar de 930 m³/s amanhã?** 930 m³/s é a cheia que volta, em média, a cada 3 anos pela curva de Gumbel do estudo de Farias e Gomes (2023, UESC), nível em que as áreas ribeirinhas já são atingidas.

Quando o risco é médio ou alto, o sistema escreve um alerta com base nos documentos de orientação da Defesa Civil, confere os números e envia pelo Telegram. Os dados dos moradores ficam protegidos no MongoDB, com um papel de acesso para cada parte do sistema, e a IA nunca enxerga mais do que o usuário que perguntou.

Não há site, aplicação web nem chat livre: as interfaces são o bot do Telegram (comandos fixos), o fluxo do n8n e o terminal (`cli.py`).

## 2. Arquitetura

O caminho de um alerta, do dado ao morador:

1. **Coleta.** Séries diárias da ANA (Hidroweb): vazão das estações Contorno da BR-101 (53180000) e Ferradas (53170000) e chuva de 6 postos pluviométricos da bacia, de 1963 a 2026. Ficam na coleção `series_hidrologicas` (153.363 leituras).
2. **Previsão.** Regressão logística com chuva acumulada de 24, 48 e 72 horas, vazão atual, variação da vazão e mês do ano. Saída: probabilidade de passar de 930 m³/s no dia seguinte; risco baixo (abaixo de 0,30), médio (0,30 a 0,60) ou alto (0,60 ou mais). Gravada em `previsoes`.
3. **Orquestração.** O n8n roda a cada 15 minutos: chama a API local (`/ciclo`), decide se há alerta e segue para os próximos passos.
4. **Geração do alerta (RAG + LLM).** A API busca os 4 trechos mais parecidos entre os 24 documentos de orientação (vetores MiniLM de 384 dimensões, calculados no próprio computador, filtrados pelo nível de risco) e o Gemini 3.5 Flash-Lite escreve o texto com o prompt versionado `prompts/alerta_v2.md`.
5. **Validador.** Confere nível, probabilidade, vazão, abrigos e telefones. Se algo não bate, ou se o Gemini não responde, sai o texto padrão do documento 24.
6. **Envio e registro.** O n8n envia no grupo do Telegram e grava o registro na `auditoria` com o usuário `svc_n8n`.
7. **Bot do morador.** `/start`, `/setor`, `/risco`, `/relato` e `/sair`. Os relatos são classificados (confirmado, observação, não relacionado) por um classificador local.
8. **Terminal do operador.** O operador pergunta em português; a IA escolhe uma entre 5 consultas prontas e a consulta roda com a senha do próprio operador. Tudo vai para a auditoria: quem perguntou, a pergunta anonimizada, o que a IA entendeu, se o banco permitiu e o que a IA respondeu.

| Peça | Tecnologia | Onde está |
|---|---|---|
| Banco | MongoDB 8.0 com autenticação, 8 coleções, 3 views, $jsonSchema e índices | `banco/` |
| Modelo de previsão | scikit-learn (regressão logística) | `src/modelo/` |
| RAG e LLM | sentence-transformers (MiniLM) e Gemini pela API REST | `src/ia/` |
| Ajuste fino | BERTimbau no Google Colab | `notebooks/` |
| Orquestração | n8n 2.x | `n8n/fluxo_alerta.json` |
| API local e bot | Python (http.server e API do Telegram) | `src/api/`, `src/bot/` |

## 3. Como instalar (Windows, uma vez só)

Pré-requisitos: Python 3.13, MongoDB Community Server 8.0 (como serviço) com mongosh, Node.js LTS (para o n8n).

```
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1          (no Linux/Mac: source .venv/bin/activate)
python -m pip install --upgrade pip
pip install -r requirements.txt
python cli.py configurar             cria o .env com senhas e chaves aleatórias (pede a chave do Gemini e o token do bot)
python cli.py criar-admin            cria o administrador do MongoDB (antes de ligar a autenticação)
```

Ligar a autenticação: no `mongod.cfg` (pasta `C:\Program Files\MongoDB\Server\8.0\bin`), trocar `#security:` por `security:` e, na linha de baixo, `  authorization: enabled`. Reiniciar o serviço (`Restart-Service MongoDB` no PowerShell como administrador). Depois:

```
python cli.py banco criar            coleções, validação, índices e views mascaradas
python cli.py banco papeis           8 papéis e 8 usuários (privilégio mínimo)
python cli.py banco carga            estações e 50 moradores e 30 relatos fictícios
python cli.py baixar-dados           séries da ANA (usa os CSVs do Hidroweb de dados/brutos, se existirem)
python cli.py carregar-dados         grava as séries no MongoDB
python cli.py treinar                treina e avalia o modelo (resultados/modelo/)
python cli.py indexar-documentos     base do RAG com os vetores
python cli.py banco auditoria-completa   view da auditoria com a pergunta e a resposta da IA
```

No `.env`, para a demonstração com a cheia de fevereiro de 2002: `REPRODUCAO_INICIO=2002-01-31` e `TELEGRAM_CHAT_ALERTAS` com o id do grupo (`python cli.py telegram-chat-id`).

## 4. Como rodar

Quatro terminais, com o ambiente ativado (`.\.venv\Scripts\Activate.ps1`):

```
python cli.py servidor                                        terminal 1: API local usada pelo n8n e pelo bot
python cli.py bot                                             terminal 2: bot do Telegram
$env:NODE_OPTIONS="--dns-result-order=ipv4first"; npx n8n     terminal 3: n8n em http://localhost:5678
Remove-Item resultados\estado_operacao.json                   terminal 4: volta a reprodução para 31/01/2002
```

No n8n, importar `n8n/fluxo_alerta.json` e criar as três credenciais (cabeçalho `X-Token` com o `API_TOKEN` do `.env`, token do bot e a connection string do usuário `svc_n8n`). Cada clique em Execute avança um dia da reprodução; no quinto (04/02/2002) o risco é alto (96%) e o alerta chega no grupo.

Terminal do operador e do auditor:

```
python cli.py status
python cli.py consulta --usuario operador_defesa_civil --senha-do-env "quais foram os últimos alertas?"
python cli.py auditoria --completo
```

### Testes e medições

```
python cli.py testar-permissoes      matriz de GRANT e DENY de cada usuário (resultados/permissoes/)
python cli.py banco volume           2,6 milhões de leituras e 300 mil alertas para medir desempenho
python cli.py banco consultas-lentas planos de execução antes e depois dos índices (resultados/banco/)
python cli.py casos                  17 casos de teste da IA com métricas (resultados/casos/)
python cli.py testar-ataques         prompt injection, injeção NoSQL e escalonamento de privilégio (resultados/ataques/)
python cli.py testar-vazamento       8 perfis x 5 perguntas: a IA não vaza o que o banco protege (resultados/vazamento/)
python cli.py avaliar-prompts        comparação das versões do prompt (resultados/prompts/)
python cli.py custo-latencia         custo por 1.000 alertas e tempo de resposta (resultados/custo_latencia/)
python cli.py verificar-segredos     procura chaves e senhas nos arquivos e no fluxo do n8n (resultados/seguranca/)
pytest                               testes automáticos (servidor compatível com MongoDB sem autenticação)
```

Ajuste fino: `notebooks/finetuning_comparacao.ipynb` no Google Colab (GPU T4) compara BERTimbau base, base com RAG, ajustado e ajustado com RAG, além do Gemini sem exemplos e com RAG.

Se o serviço automático da ANA estiver fora do ar (HTTP 504), baixe as séries em www.snirh.gov.br/hidroweb/serieshistoricas (CSV) e coloque os arquivos `CODIGO_Vazoes.csv` e `CODIGO_Chuvas.csv` em `dados/brutos`.

## 5. Estrutura do projeto

```
cli.py                  todos os comandos do projeto e o terminal do operador
src/coleta/             leitura das séries da ANA (serviço e CSV do Hidroweb) e carga no MongoDB
src/modelo/             limiares de Gumbel do estudo da UESC, variáveis, treino e previsão
src/ia/                 RAG, Gemini, validador, alerta, consulta com permissões, classificador de relatos
src/api/  src/bot/      API local (usada pelo n8n e pelo bot) e bot do Telegram
src/permissoes.py       teste de GRANT e DENY por usuário
src/ataques.py          ataques testados e defesas
src/vazamento.py        prova, por perfil, de que a IA não vaza dado protegido
src/segredos.py         verificação de segredos no repositório e no fluxo do n8n
src/casos.py            casos de teste da IA com métricas
src/seguranca.py        hash, criptografia AES-256-GCM, anonimização e validação de entrada
banco/                  scripts do mongosh: 01 criação, 02 carga, 03 papéis, 04 volume, 05 consultas lentas, 06 auditoria completa
prompts/                prompts versionados e HISTORICO.md
n8n/fluxo_alerta.json   fluxo do n8n exportado (credenciais só por referência)
notebooks/              ajuste fino do BERTimbau e comparação final (Colab)
dados/                  documentos do RAG, relatos fictícios (treino e teste difícil), séries da ANA
resultados/             métricas, figuras, casos, permissões, ataques, vazamento, planos de execução
testes/                 testes automáticos (pytest), com simulador de papéis e serviços falsos
```

## 6. Segurança

- Senhas, chaves de API, a chave de criptografia e o sal ficam no `.env`, que está no `.gitignore`. O comando `verificar-segredos` confere que nenhum valor do `.env` aparece nos arquivos do repositório nem no fluxo do n8n.
- O id do Telegram de cada morador é guardado como hash SHA-256 com sal e cifrado com AES-256-GCM; o texto original dos relatos também é cifrado, e o que circula é a versão anonimizada.
- Operador e auditor só leem views mascaradas (apelido, IP). Nenhum papel administra usuários, papéis ou a auditoria.
- A IA escolhe uma consulta pronta, nunca monta filtro com o texto do usuário, e a consulta roda com a credencial de quem perguntou.
- Moradores e relatos usados no projeto são fictícios. Os únicos dados reais são as séries públicas da ANA.
