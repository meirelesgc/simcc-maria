# SIMCC Maria

Chatbot no terminal para perguntas em linguagem natural sobre bolsistas por cotas
(IC, mestrado e doutorado) e a produção científica associada a eles no SIMCC.

> **A base identifica bolsistas, não bolsas.** Contamos pessoas e registros de
> bolsistas; não é possível dizer quantas bolsas existem nem quais registros
> pertencem à mesma bolsa.

```bash
poetry install --with docs,dev
poetry run ingest       # data/raw/scholarships.parquet -> holder_records (data/processed)
poetry run load-db      # schema maria no Postgres: tabelas, embeddings, ligações, funções
poetry run maria        # chat
poetry run maria-web    # chat no navegador (http://localhost:8001); Docker: docker compose up -d --build
poetry run evaluate     # avaliação com respostas conhecidas
poetry run pytest       # testes
poetry run mkdocs serve # documentação em http://127.0.0.1:8000
```

Requer `.env` com `DATABASE_URL` e `OPENAI_API_KEY`.

**Sem Python na máquina** (só Docker, com a stack do SIMCC rodando): `bin/setup`
constrói a imagem de ferramentas e roda `ingest`, `load-db` e os testes.
Qualquer comando acima roda com `bin/run` no lugar de `poetry run`
(`bin/run maria`, `bin/run load-db --from links`, `bin/run pytest`;
`bin/run docs` serve a documentação). O repositório é montado no container,
então mudanças no código valem sem rebuild; após mudar dependências, rode
`docker compose --profile tools build tools`.

## Dados

| Arquivo | Conteúdo |
|---|---|
| `data/raw/scholarships.parquet` | 45.425 linhas → 43.176 registros de bolsistas, de 32.959 pessoas |

Veja `docs/dados/visao-geral.md`.

## Relatório: conversão CPF → Lattes ID (05/10/2026)

A planilha de projetos chegou com o **CPF** do bolsista. O CPF foi trocado
pelo Lattes ID por meio da API do SIMCC (`/v3/api/getIdentificadorCNPq`), e a
planilha original foi apagada. O resultado hoje é `data/raw/scholarships.parquet`,
com as colunas e os status já traduzidos para o padrão do repositório.

### Resultado

| `lattes_status` | Linhas | CPFs distintos | Significado |
|---|---:|---:|---|
| `found` | 45.317 (99,8%) | 32.856 | Lattes encontrado |
| `not_found` | 105 | 91 | a API respondeu `500 Error processing CNPq request` em duas rodadas |
| `foreign_document` | 3 | 2 | passaporte em vez de CPF; não consultado |
| **Total** | **45.425** | **32.949** | |

- **Requisições:** 32.947, uma por CPF distinto, em vez de 45.425 (uma por
  linha). Foram cerca de 35 minutos a ~16 req/s, com 8 conexões simultâneas.
- **Lattes distintos na saída:** 32.857.
- **Formato:** Parquet com zstd (16 MB, contra 70 MB em CSV). O conteúdo foi
  verificado como idêntico ao do CSV.

### Privacidade

- **A saída não tem coluna de CPF.**
- **CPF e RG digitados em texto livre** ("Resumo do Projeto") foram
  substituídos por `[CPF removido]` / `[RG removido]` em 3 células. O critério:
  número precedido de "CPF", ou sequência com dígito verificador de CPF
  válido. Códigos como CAAE e PROSPERO foram preservados.
- **Verificação final:** nenhum CPF da planilha original aparece no arquivo,
  nem como célula nem dentro de textos.
- **A planilha original foi removida do disco e do histórico do Git**
  (commit reescrito e objetos órfãos eliminados antes de qualquer push).
- **O cache da conversão** (SHA-256 do CPF → Lattes) **foi apagado**. Um hash
  de CPF pode ser revertido por força bruta.
- **Nenhum CPF foi exibido durante o processo**, apenas contagens e formatos
  mascarados.

### Limitações

- **As 108 linhas sem Lattes** (105 não encontradas + 3 com documento
  estrangeiro) **não podem mais ser ligadas a um pesquisador**, porque a
  planilha original não existe mais.
- **Uma planilha nova com CPFs precisa passar pelo mesmo processo:**

  ```bash
  poetry run resolve-lattes ENTRADA.xlsx data/raw/scholarships.parquet
  ```

  Em seguida, apague a entrada e o diretório `data/cache/`. Detalhes em
  `docs/dados/pipeline.md`.

## Melhorias futuras

### Embeddings nas views materializadas do SIMCC

**Pergunta:** vale colocar os embeddings nas views materializadas (`mv_search_*`,
`mv_canonical_*`) no lugar de `search_document_researcher` e
`search_document_production`?

**É possível, mas não diretamente.** Uma view materializada é o resultado de
uma consulta SQL, e o embedding vem de uma API externa (OpenAI). O `REFRESH`
não consegue gerá-lo. O que dá para fazer é **juntar** na view embeddings já
guardados numa tabela.

O desenho recomendado, o mesmo que o `maria` usa em `maria.embedding_cache`:

1. **Uma tabela de embeddings indexada pelo hash do texto** (`sha256(modelo +
   texto)`). Um job gera apenas os hashes que ainda não existem, antes do
   `REFRESH`.
2. **A view materializada guarda só a chave** (o hash do texto que ela
   monta), não o vetor. A busca faz `JOIN` com a tabela de embeddings.
3. **O índice HNSW fica na tabela de embeddings,** que é estável, e não na
   view.

Por que não guardar o vetor dentro da view:

- **Cada `REFRESH` reescreveria todos os vetores** (`search_document_production`
  já ocupa 1,1 GB) e **reconstruiria o índice HNSW** do zero. Neste banco isso
  leva de 6 a 20 minutos.
- **Não há atualização incremental:** um texto alterado obriga a recalcular a
  view inteira.

Ganhos adicionais observados no dump:

- **Embeddings por obra canônica.** Hoje há um vetor por cópia da produção (uma
  por coautor). Usando as `mv_canonical_*` (que já deduplicam), seriam menos
  vetores, e a deduplicação ficaria alinhada com a contagem de obras.
- **Índice vetorial.** `search_document_production` não tem índice HNSW/IVFFlat,
  então toda busca semântica percorre a tabela inteira.
- **Busca híbrida nativa.** As views já têm `tsvector` com índice GIN. Combinar
  `ts_rank` com o cosseno daria uma busca híbrida melhor que o `LIKE` usado
  hoje em `maria.search_*`.
- **`maria.productions` poderia usar as `mv_canonical_*`** em vez da `work_key`
  própria (DOI ou título + ano).
