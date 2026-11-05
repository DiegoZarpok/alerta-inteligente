# Alerta Inteligente: Previsão de Cheias do Rio Cachoeira (Itabuna-BA)

Grupo Sentinela do Cachoeira. SIS939 - Projeto de Inteligência Artificial, integrado com SIS913 - Bancos de Dados NoSQL. Unex Itabuna.

Componentes: Diego Ailton Silva Barbosa, Pedro Henrique Costa, Alexandre Pereira Muniz e Marcos Vinicius Farias Silva.

## O que o sistema faz

Itabuna sofre com cheias do Rio Cachoeira desde pelo menos 1914. O sistema calcula, a partir de dados públicos da ANA, a probabilidade de a vazão na estação Contorno da BR-101 (53180000) passar no dia seguinte de 930 m³/s, a cheia de 3 anos de retorno pela curva de Gumbel do estudo de Farias e Gomes (2023, UESC). Quando o risco é médio ou alto, o Gemini escreve o alerta com base em 24 documentos de orientação (RAG), um validador confere os números e o alerta sai pelo Telegram. Tudo fica registrado no MongoDB, com papéis de acesso separados para cada parte do sistema.

Não há site nem chat livre: a interface é o bot do Telegram, com comandos fixos, e o terminal (`cli.py`).

## Como rodar

Pré-requisitos: Python 3.13 (no 3.15 a biblioteca pyyaml ainda precisa ser compilada), MongoDB Community 8.0 com mongosh, Node.js 20 ou 22 (para o n8n). O passo a passo detalhado para Windows está em `docs/entrega2/` e no relatório da entrega.

```
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1          (no Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python cli.py configurar             cria o .env com senhas e chaves aleatórias
python cli.py criar-admin            cria o administrador do MongoDB (antes de ligar a autenticação)
                                     ligar "security: authorization: enabled" no mongod.cfg e reiniciar o serviço
python cli.py banco criar            coleções, validação, índices e views mascaradas
python cli.py banco papeis           papéis e usuários (privilégio mínimo)
python cli.py banco carga            estações e moradores/relatos fictícios
python cli.py baixar-dados           séries reais da ANA (ou os CSVs do Hidroweb colocados em dados/brutos)
python cli.py carregar-dados         grava as séries no MongoDB
python cli.py treinar                treina e avalia o modelo (resultados/modelo/)
python cli.py indexar-documentos     monta a base do RAG com os vetores
python cli.py testar-permissoes      evidência de acesso permitido e negado
python cli.py banco volume           gera volume para os testes de desempenho
python cli.py banco consultas-lentas planos de execução antes e depois dos índices
python cli.py servidor               API local (deixar aberto)
python cli.py bot                    bot do Telegram (deixar aberto, em outro terminal)
npx n8n                              importar n8n/fluxo_alerta.json (no PowerShell, se o Telegram der
                                     timeout: $env:NODE_OPTIONS="--dns-result-order=ipv4first"; npx n8n)
python cli.py casos                  casos de teste da IA
python cli.py avaliar-prompts        compara as versões do prompt
python cli.py custo-latencia         mede custo e tempo de resposta
```

Terminal do operador: `python cli.py status`, `python cli.py consulta --usuario operador_defesa_civil "quais foram os últimos alertas?"` e `python cli.py auditoria`. A consulta pede a senha do usuário; para demonstração, `--senha-do-env` usa a senha desse usuário guardada no `.env` (a conexão continua sendo a dele).

Se o serviço automático da ANA estiver fora do ar (HTTP 504), baixe as séries em www.snirh.gov.br/hidroweb/serieshistoricas (formato CSV), e coloque os arquivos `CODIGO_Vazoes.csv` e `CODIGO_Chuvas.csv` em `dados/brutos`. O `baixar-dados` usa esses arquivos e descarta os dias sem leitura (status diferente de 1, 2 ou 3).

O ajuste fino do BERTimbau roda no Google Colab: `notebooks/finetuning_bertimbau.ipynb`.

## Estrutura

```
cli.py                  comandos do projeto e terminal do operador
src/coleta/             download das séries da ANA e carga no MongoDB
src/modelo/             limiares do estudo da UESC, variáveis, treino e previsão
src/ia/                 RAG, Gemini, validador, alerta, consulta com permissões, classificador de relatos
src/api/ src/bot/       API local (usada pelo n8n e pelo bot) e bot do Telegram
src/permissoes.py       teste automático de GRANT e DENY
banco/                  scripts do mongosh (criação, carga, papéis, volume, consultas lentas)
prompts/                prompts versionados e HISTORICO.md
n8n/fluxo_alerta.json   fluxo do n8n (gatilho, IA, ação, registro)
notebooks/              ajuste fino do BERTimbau (Colab)
dados/                  documentos do RAG, relatos fictícios, séries da ANA
resultados/             métricas, figuras, casos de teste, permissões, planos de execução
testes/                 testes automáticos (pytest)
```

## Segurança

Senhas, chaves de API, a chave de criptografia e o sal ficam no `.env`, que está no `.gitignore`. O identificador do Telegram de cada morador é guardado com hash SHA-256 com sal e criptografado com AES-256-GCM; operador e auditor só leem views mascaradas. O Gemini recebe apenas números públicos e trechos dos documentos. Os moradores e relatos usados no projeto são fictícios.

Ferramenta experimental de estimativa de risco. Não substitui a Defesa Civil (199).
