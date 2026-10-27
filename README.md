# Alerta Inteligente: Previsão de Cheias do Rio Cachoeira (Itabuna-BA)

Grupo Sentinela do Cachoeira, SIS939 - Projeto de Inteligência Artificial, Unex Itabuna.
Projeto integrado com SIS913 - Bancos de Dados NoSQL.

Componentes: Diego Ailton Silva Barbosa, Pedro Henrique Costa, Alexandre Pereira Muniz e Marcos Vinicius Farias Silva.

## Problema

Itabuna sofre com cheias do Rio Cachoeira desde pelo menos 1914. Em dezembro de 2021 o rio subiu cerca de 9 metros. Hoje o morador só percebe a cheia quando a água já está chegando.

O sistema é pensado para os moradores das áreas ribeirinhas e para a Defesa Civil. Funcionando, o aviso chega com até 24 horas de antecedência, tempo suficiente para tirar documentos, móveis e pessoas das áreas de risco.

## Como funciona

1. Coleta: um fluxo no n8n busca a cada hora a vazão e a cota do rio (ANA, estação Ferradas 53170000) e a chuva da bacia (INMET e CEMADEN).
2. Modelo de previsão: Regressão Logística e Random Forest (scikit-learn) calculam a probabilidade de a vazão passar de 2.430 m³/s nas próximas 24 horas. Esse limiar de transbordamento vem de um estudo da UESC (2023). O resultado vira um nível de risco: baixo, médio ou alto.
3. LLM com RAG: quando o risco é médio ou alto, o Gemini 2.5 Flash escreve o alerta em linguagem simples, usando 24 documentos de orientação guardados no MongoDB Atlas (busca vetorial). Um validador confere se os números do texto são os mesmos calculados pelo modelo.
4. Envio e registro: o alerta sai pelo bot do Telegram e fica registrado no MongoDB.
5. Fine-tuning: experimento com BERTimbau para classificar relatos de moradores, comparado ao Gemini sem treino.

O projeto não tem site nem chat livre. A interface é o bot do Telegram, com comandos fixos, e o terminal do operador.

## Tecnologias

Python 3.11, Pandas, NumPy, scikit-learn, Matplotlib, MongoDB Atlas (Vector Search), sentence-transformers, Gemini API, n8n, Telegram Bot API e Hugging Face Transformers (Google Colab).

## Estrutura do repositório

```
banco/                  scripts do MongoDB (criação, carga, papéis, volume e consultas lentas)
dados/documentos_rag/   24 documentos da base do RAG e INDICE.md com a origem de cada um
docs/entrega1/          PDF da Entrega 1, canvas, diagrama de arquitetura e diagrama integrado
REGISTRO.md             histórico do projeto
.env.example            modelo das variáveis de ambiente, sem chaves reais
```

## Banco de dados

No mongosh, aberto na pasta do projeto, rodar em ordem:

```
load("banco/01_criar_banco.js")      // coleções, validação, índices e views mascaradas
load("banco/02_carga_inicial.js")    // carga inicial (precisa de ALERTA_CHAVE e ALERTA_SAL)
load("banco/03_papeis_usuarios.js")  // papéis e usuários com privilégio mínimo
load("banco/04_gerar_volume.js")     // volume para os testes de desempenho
load("banco/05_consultas_lentas.js") // consultas lentas antes e depois dos índices
```

## Segurança

Chaves de API, senhas, a chave de criptografia e o sal do hash ficam no arquivo `.env`, que está no `.gitignore` e não vai para o GitHub. Os dados de rio e chuva são públicos. Os dados de moradores usados nesta fase são fictícios; no banco, o identificador do Telegram é guardado com hash e criptografia, e operador e auditor só leem views mascaradas.

## Versão mínima (3 semanas)

Histórico carregado no MongoDB, modelo treinado e avaliado, e fluxo do n8n rodando de hora em hora, calculando o risco, gerando o texto com RAG, enviando no Telegram e registrando o alerta.

Ferramenta experimental de estimativa de risco. Não substitui a Defesa Civil (199).
