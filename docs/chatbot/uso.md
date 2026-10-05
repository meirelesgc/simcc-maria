# Como usar

## Preparação (uma vez)

```bash
poetry install --with docs,dev
poetry run ingest      # data/raw/scholarships.parquet → bolsas e bolsistas
poetry run load-db     # schema maria no Postgres (~40 min na 1ª vez; depois usa o cache)
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
| `/exemplos` | perguntas sugeridas, incluindo a pergunta-guia sobre Dengue |
| `/schema` | tabelas, views e funções que o modelo conhece |
| `/sql` | liga/desliga o SQL de cada passo |
| `/csv` | exporta o resultado de **todos os passos** da última resposta para `logs/exports/` |
| `/log` | mostra o arquivo de log da sessão |
| `/limpar` | esquece o contexto (perguntas de seguimento) |
| `/sair` | encerra (Ctrl+D também) |

### Como ler uma resposta

O modelo faz **várias consultas** antes de responder, e cada uma aparece na
tela assim que termina:

```
╭─ passo 1 · Buscar bolsas sobre dengue (lexical + semântica) ──────────╮
│ SELECT match_method, count(*) AS bolsas, sum(g.holder_count) AS ...   │
│ FROM maria.search_grants(ARRAY['dengue','aedes aegypti'], :tema) s    │
│ :tema = embedding("dengue e arboviroses")                             │  ← texto embedado
│  match_method   bolsas   bolsistas                                    │
│  lexical           ...      ...      ███████                          │
╰─────────────────────────────────────────────────── 3 linhas · 410 ms ╯
╭─ passo 2 · ... ─╮
...
╭─ resposta ────────────────────────────────────────────────────────────╮
│ **Sim.** ... bolsas sobre dengue ...                                  │
│ ⚠ números não encontrados nos resultados: ...                         │  ← conferência automática
╰─────────────────────────── 5 passos · 31.200 tokens · 48s · gpt-5.5 ─╯
```

- **Título de cada passo:** o que o modelo quis verificar com aquela consulta.
- **`:nome = embedding("…")`:** o texto usado na busca semântica daquele passo.
- **⚠ números não encontrados:** a resposta citou um número que não aparece em
  nenhum resultado. Desconfie dele.
- **⚠ limite de passos:** o modelo chegou ao máximo de consultas e respondeu
  com o que tinha.

## Avaliação

```bash
poetry run evaluate                # todos os casos
poetry run evaluate --runs 3       # consistência
poetry run evaluate -k dengue      # só casos com "dengue" no id
```

Os valores esperados vêm do **polars** (contagens de bolsas e bolsistas) ou de
um **SQL de referência** escrito à mão (resultado temático, com termos fixados
na pergunta). A verificação procura os números **no texto da resposta final**.

A pergunta-guia completa (`dengue_question`) não tem resposta única, porque
depende dos sinônimos que o modelo escolhe. Por isso ela é marcada para
**revisão manual**. O avaliador só confere se houve resposta, se o limite de
passos não foi atingido e se não há números sem lastro.

## Ajustar a busca híbrida

As linhas de corte e os pesos estão em [Pipeline ›
Parâmetros](../dados/pipeline.md#parametros-env). Por exemplo, para ser mais
exigente na busca semântica de temas:

```bash
THEME_SEMANTIC_MIN=0.45 poetry run load-db     # recria as funções com o novo padrão
poetry run evaluate -k dengue
```

## Testes

```bash
poetry run pytest
```

Os testes cobrem as regras de identidade da bolsa (vários bolsistas,
duplicatas, ciclos), os placeholders de embedding, a conferência de números,
a máscara de CPF e os próprios verificadores da avaliação. Nenhum teste chama
o LLM nem o banco.
