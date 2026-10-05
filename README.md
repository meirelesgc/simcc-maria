# SIMCC Maria

Chatbot no terminal para perguntas em linguagem natural sobre as bolsas de produtividade do CNPq (PQ/DT).

```bash
poetry install --with docs,dev
poetry run ingest       # data/raw/raw-data.xlsx -> data/processed/bolsas_pq_dt.csv
poetry run load-db      # CSV -> maria.bolsas (Postgres)
poetry run maria        # chat
poetry run evaluate     # avaliação com respostas conhecidas
poetry run pytest       # testes
poetry run mkdocs serve # documentação em http://127.0.0.1:8000
```

Requer `.env` com `DATABASE_URL` e `OPENAI_API_KEY`.

## Dados

| Arquivo | Conteúdo |
|---|---|
| `data/raw/raw-data.xlsx` | Bolsas PQ/DT do CNPq vigentes em 08/09/2026 (17.945 linhas) |
| `data/raw/bolsas_projetos.parquet` | Projetos de pesquisa com o Lattes ID do pesquisador (45.425 linhas) |

## Relatório: conversão CPF → Lattes ID (05/10/2026)

A planilha de projetos chegou com o **CPF** do pesquisador. O CPF foi trocado
pelo Lattes ID por meio da API do SIMCC (`/v3/api/getIdentificadorCNPq`), e a
planilha original foi apagada.

### Resultado

| `lattes_status` | Linhas | CPFs distintos | Significado |
|---|---:|---:|---|
| `ok` | 45.317 (99,8%) | 32.856 | Lattes encontrado |
| `nao_encontrado` | 105 | 91 | a API respondeu `500 Error processing CNPq request` em duas rodadas |
| `documento_estrangeiro` | 3 | 2 | passaporte em vez de CPF; não consultado |
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
  poetry run resolve-lattes ENTRADA.xlsx data/raw/SAIDA.parquet
  ```

  Em seguida, apague a entrada e o diretório `data/cache/`. Detalhes em
  `docs/dados/pipeline.md`.
