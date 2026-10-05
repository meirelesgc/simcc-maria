# SIMCC (fonte complementar)

!!! info "Prioridade"
    A fonte principal é a [planilha do CNPq](visao-geral.md). O SIMCC serve
    para enriquecer: produção científica e perfil dos bolsistas que existem
    nas duas bases.

## Conexão

Banco Postgres 17 com as extensões `vector` (pgvector 0.8), `pg_trgm` e
`unaccent`. A URL fica no `.env`, que não é versionado:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/simcc
```

É um dump local. Os documentos foram indexados entre 17/08/2026 e 08/09/2026.

## Cobertura: o SIMCC é recortado na Bahia

| | Pesquisadores |
|---|---:|
| `researcher` no SIMCC | 12.009 |
| Bolsistas na planilha | 17.940 |
| **Nas duas bases** (por `lattes_id`) | **443 (2,5% da planilha)** |

O SIMCC cobre sobretudo instituições baianas (UFBA, UNEB, IFBA, UESB, UFRB,
UEFS, UESC, UFSB…). Dos 443 bolsistas em comum, 420 estão na BA.

!!! warning "Consequência para o chatbot"
    Perguntas que cruzam bolsa e produção ("bolsistas PQ que publicam sobre
    X") só têm resposta para ~2,5% dos bolsistas. O chatbot precisa dizer isso
    na resposta, para não dar a entender que cobre o Brasil todo.

## Tabelas com embeddings

Os embeddings têm **1536 dimensões**. Não há índice vetorial (HNSW/IVFFlat),
então a busca é sequencial. Nesse volume, isso é aceitável para o MVP.

### `search_document_researcher`: 12.009 linhas, 1 por pesquisador

| Coluna | Tipo | Observação |
|---|---|---|
| `researcher_id` | uuid | → `researcher.id` (único) |
| `document_content` | text | Texto indexado: nome, instituição, áreas de atuação… |
| `embedding` | vector(1536) | |
| `last_indexed_at` | timestamp | |

### `search_document_production`: 135.658 linhas, 1 por produção

| `type` | Linhas | Tabela de origem (`production_id` →) |
|---|---:|---|
| ARTICLE | 90.171 | `bibliographic_production.id` |
| BOOK_CHAPTER | 31.629 | `bibliographic_production.id` |
| BOOK | 9.941 | `bibliographic_production.id` |
| REPORT | 1.941 | `research_report.id` |
| SOFTWARE | 1.235 | `software.id` |
| PATENT | 741 | `patent.id` |

`_search_document_production` tem a mesma estrutura e está vazia. Parece ser
uma tabela de staging.

## Da produção ao bolsista da planilha

```mermaid
flowchart LR
    SDP[search_document_production] -->|production_id| BP[bibliographic_production<br/>software · patent · research_report]
    BP -->|researcher_id| R[researcher]
    SDR[search_document_researcher] -->|researcher_id| R
    R -->|lattes_id = id_lattes| CSV[(planilha CNPq)]
```

```sql
-- artigos mais próximos de um vetor, com o lattes do autor
SELECT r.lattes_id, r.name, b.title, b.year
FROM search_document_production s
JOIN bibliographic_production b ON b.id = s.production_id
JOIN researcher r ON r.id = b.researcher_id
WHERE s.type = 'ARTICLE'
ORDER BY s.embedding <=> $1
LIMIT 10;
```

## Tabela `foment`: bolsas que o SIMCC já tem

O SIMCC tem sua própria tabela `foment`, com 413 linhas e a mesma ideia da
planilha, mas mais pobre: sem `call_title`, sem `funding_program_name`, e com
o nível embutido no nome (`Produtividade em Pesquisa - 1C`). Desses 413
pesquisadores, 387 estão na planilha. Os outros 26 provavelmente têm bolsas já
encerradas. **A planilha é a fonte de verdade para bolsas.**

## Outras tabelas úteis

Todas se ligam a `researcher.id` por `researcher_id`:

- **Perfil:** `researcher` (inclui `abstract`, `orcid`, `qtt_publications`), `researcher_production` (contagens por tipo), `researcher_area_expertise`
- **Vínculos:** `graduate_program_researcher`, `research_group_researcher`, `researcher_institution`
- **Atividades:** `guidance` (orientações), `research_project`, `education`
