# SIMCC Maria

Chatbot no terminal para perguntas em linguagem natural sobre **bolsistas por
cotas** (IC, mestrado e doutorado) e a **produção científica** associada a
eles no SIMCC.

!!! important "Bolsistas, não bolsas"
    A base identifica quem recebeu bolsa, mas não identifica as bolsas. O
    chatbot conta bolsistas e registros, e explica essa distinção quando
    perguntam por bolsas.

!!! info "Pergunta-guia"
    *As bolsas contemplam pesquisas na temática Dengue? Se sim, qual o resultado
    desse fomento? Ele gerou artigos? livros? capítulos? de quem, quando e
    quantos?*

## Fontes de dados

| Fonte | Conteúdo | Documentação |
|---|---|---|
| `data/raw/scholarships.parquet` | 43.176 registros de 32.959 bolsistas (a base não identifica bolsas) | [Visão geral](dados/visao-geral.md) · [Análise](dados/analise.md) · [Limpezas](dados/limpeza.md) |
| SIMCC (Postgres + pgvector) | pesquisadores, orientações, produções e embeddings | [SIMCC](dados/simcc.md) |

## Estrutura do repositório

```text
simcc-maria/
├── data/
│   ├── raw/scholarships.parquet   # bolsistas com Lattes (sem CPF)
│   ├── processed/                 # gerado por `ingest` (não versionado)
│   └── cache/                     # caches locais (não versionado)
├── docs/                          # esta documentação (MkDocs)
├── logs/                          # auditoria: um JSONL por sessão (não versionado)
├── src/simcc_maria/
│   ├── config.py                  # parâmetros (pydantic-settings, lê o .env)
│   ├── resolve_lattes.py          # CPF → Lattes (API do SIMCC)
│   ├── ingest.py                  # planilha → registros de bolsistas (polars)
│   ├── embeddings.py              # embeddings OpenAI com cache no Postgres
│   ├── load_db.py                 # schema maria: tabelas, ligações, funções
│   ├── catalog.py                 # o que o LLM sabe do banco + regras
│   ├── db.py                      # execução SQL somente leitura
│   ├── agent.py                   # loop de ferramentas: pergunta → consultas → resposta
│   ├── audit.py                   # log JSONL
│   ├── cli.py                     # chat no terminal
│   ├── web.py                     # chat no navegador (static/index.html)
│   └── evaluate.py                # perguntas com resposta conhecida
├── tests/
├── compose.yaml · Dockerfile     # interface web em Docker
├── mkdocs.yml
└── pyproject.toml
```

## Comandos

```bash
poetry install --with docs,dev  # dependências + documentação + testes
poetry run ingest               # registros de bolsistas em data/processed
poetry run load-db              # schema maria no Postgres
poetry run maria                # chat
poetry run maria-web            # chat no navegador (docker compose up -d --build)
poetry run evaluate             # avaliação
poetry run pytest               # testes
poetry run mkdocs serve         # documentação em http://127.0.0.1:8000
```
