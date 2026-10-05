# SIMCC Maria

Chatbot para fazer perguntas em linguagem natural sobre dados de fomento à
pesquisa e receber de volta uma **listagem** ou uma **agregação com resumo**.

!!! info "Status: MVP v1 no terminal"
    O chat sobre a planilha funciona (`poetry run maria`) e acerta 16/16 das
    perguntas de avaliação. Veja [como usar](chatbot/uso.md) e a
    [arquitetura](chatbot/arquitetura.md). A integração com o SIMCC é a fase 2.

## Fontes de dados

| Fonte | Situação | Documentação |
|---|---|---|
| Planilha CNPq: bolsas PQ/DT vigentes | ✅ disponível | [Visão geral](dados/visao-geral.md) |
| SIMCC (Postgres + pgvector) | ➕ complementar, 2,5% de sobreposição | [SIMCC](dados/simcc.md) |

## Estrutura do repositório

```text
simcc-maria/
├── data/
│   ├── raw/                 # arquivos originais, nunca editados à mão
│   │   └── raw-data.xlsx
│   └── processed/           # gerado por `poetry run ingest`
│       └── bolsas_pq_dt.csv
├── docs/                    # esta documentação (MkDocs)
├── logs/                    # auditoria: um JSONL por sessão (não versionado)
├── src/simcc_maria/
│   ├── config.py            # configurações (pydantic-settings, lê o .env)
│   ├── ingest.py            # xlsx → csv (polars)
│   ├── catalog.py           # descrição das colunas e regras de negócio
│   ├── load_db.py           # csv → maria.bolsas (Postgres)
│   ├── db.py                # execução SQL somente leitura
│   ├── pipeline.py          # pergunta → SQL → resultado → resumo
│   ├── audit.py             # log JSONL
│   ├── cli.py               # chat no terminal
│   └── evaluate.py          # perguntas com resposta conhecida
├── tests/
├── mkdocs.yml
└── pyproject.toml
```

## Comandos

```bash
poetry install --with docs,dev  # dependências + documentação + testes
poetry run ingest               # regenera data/processed/bolsas_pq_dt.csv
poetry run load-db              # carrega o CSV em maria.bolsas
poetry run maria                # chat
poetry run evaluate             # avaliação
poetry run pytest               # testes
poetry run mkdocs serve         # documentação em http://127.0.0.1:8000
```
