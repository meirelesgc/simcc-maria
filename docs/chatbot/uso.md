# Como usar

## Preparação (uma vez)

```bash
poetry install --with docs,dev
poetry run ingest      # data/raw/raw-data.xlsx → data/processed/bolsas_pq_dt.csv
poetry run load-db     # CSV → tabela maria.bolsas no Postgres (recria a tabela)
```

O `.env` precisa ter:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/simcc
OPENAI_API_KEY=...
```

## Chat

```bash
poetry run maria
```

| Comando | O que faz |
|---|---|
| `/exemplos` | perguntas sugeridas |
| `/schema` | colunas da tabela e suas descrições |
| `/sql` | liga/desliga o painel de SQL |
| `/csv` | exporta o último resultado completo para `logs/exports/` |
| `/log` | mostra o arquivo de log da sessão |
| `/limpar` | esquece o contexto (perguntas de seguimento) |
| `/sair` | encerra (Ctrl+D também) |

Use ↑/↓ para navegar no histórico e Ctrl+R para buscar nele. O histórico fica
em `.maria_history`.

### Como ler uma resposta

```
╭─ SQL · agregacao ─────────────────────────────────────────╮
│ SELECT instituicao, COUNT(DISTINCT id_lattes) AS bolsistas │
│ ...                                                        │
│ Interpretei "bolsistas" como pessoas distintas...          │  ← premissas
╰────────────────────────────────────────── 10 linhas · 13 ms ╯
 instituicao                               bolsistas
 ───────────────────────────────────────────────────
 Universidade Federal de Pernambuco UFPE         400  ████████████████████
 ...
╭─ resumo ──────────────────────────────────────────────────╮
│ A UFPE lidera com 400 bolsistas, seguida pela UFC...       │
│ ⚠ números não encontrados na tabela: 12                    │  ← conferência automática
╰───────────────────────── 3.016 tokens · 6.2s · gpt-5.5-… ─╯
```

- **Premissas:** como o modelo interpretou a pergunta. Confira sempre.
- **Barras:** aparecem em agregações com até 20 grupos.
- **Legenda abaixo de listagens:** colunas com o mesmo valor em todas as
  linhas (os filtros aplicados).
- **⚠ números não encontrados:** o resumo citou um número que não está na
  tabela. Desconfie desse número.

## Avaliação

```bash
poetry run evaluate                  # 16 perguntas com resposta conhecida
poetry run evaluate --runs 3         # consistência: cada pergunta 3 vezes
poetry run evaluate -k nivel         # só casos com "nivel" no id
```

As respostas esperadas são calculadas **em polars a partir do CSV**, sem
passar pelo banco nem pelo LLM. Os casos ficam em `src/simcc_maria/evaluate.py`.
Para adicionar um caso, escreva a pergunta e a expressão polars que dá a
resposta certa.

### Comparar modelos

Variáveis de ambiente sobrescrevem o `.env`:

```bash
LLM_MODEL_SUMMARY=openai:gpt-5.4-mini-2026-03-17 poetry run evaluate --runs 3
LLM_REASONING_SQL=low poetry run evaluate --runs 3
```

| Variável | Padrão | Papel |
|---|---|---|
| `LLM_MODEL_SQL` | `openai:gpt-5.5-2026-04-23` | gera o SQL (etapa crítica) |
| `LLM_MODEL_SUMMARY` | igual ao de SQL | escreve o resumo |
| `LLM_REASONING_SQL` | `medium` | esforço de raciocínio no SQL |
| `LLM_REASONING_SUMMARY` | `low` | esforço de raciocínio no resumo |

## Testes

```bash
poetry run pytest
```

Os testes cobrem o CSV processado, a conferência de números e os próprios
verificadores da avaliação, para garantir que eles **reprovam** respostas
erradas. Nenhum teste chama o LLM.
