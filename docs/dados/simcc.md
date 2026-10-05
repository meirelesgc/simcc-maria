# SIMCC e ligações

O SIMCC é a fonte da **produção científica** (artigos, livros, capítulos) e
das **orientações** que ligam as bolsas aos pesquisadores.

## Conexão

Banco Postgres 17 com as extensões `vector` (pgvector 0.8), `pg_trgm` e
`unaccent`. A URL fica no `.env`, que não é versionado:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/simcc
```

É um dump local. Os documentos foram indexados entre 17/08/2026 e 08/09/2026.
O chatbot **só lê** o schema `public`; tudo o que é derivado fica no schema
`maria`.

## O que usamos do SIMCC

| Tabela | Linhas | Uso |
|---|---:|---|
| `researcher` | 12.009 | pesquisadores (`lattes_id`, nome), quase todos de instituições baianas |
| `guidance` | 422.860 | orientações: título, natureza, ano, orientador |
| `bibliographic_production` | 295.095 (artigos, livros, capítulos) | produção, um registro por coautor |
| `search_document_production` | 135.658 | embeddings (`text-embedding-3-small`, 1536 dim.) de 131 mil produções |

| Tipo | Registros | Obras distintas (`work_key`) |
|---|---:|---:|
| Artigos | 207.270 | 155.541 |
| Capítulos | 66.095 | 56.903 |
| Livros | 21.730 | 18.300 |

A diferença entre registros e obras vem dos coautores: a mesma obra aparece
uma vez para cada autor cadastrado.

## Ligação bolsa → pesquisador

```mermaid
flowchart LR
    G[maria.grants] --> H[maria.grant_holders]
    H -->|lattes_id| R[(public.researcher)]
    G -->|título ≈ título da orientação<br/>lexical OU semântico| GT[maria.guidance_titles]
    GT -->|orientador| R
    R --> P[maria.productions]
```

### Pelo bolsista (`role = 'holder'`)

Os bolsistas são estudantes, e poucos estão no SIMCC:

| | Valor |
|---|---:|
| Pessoas bolsistas que estão no SIMCC | 1.235 de 32.959 (3,7%) |
| Bolsas ligadas por um bolsista | 1.657 |

### Pelo orientador (`role = 'advisor'`)

Uma bolsa é ligada a um orientador quando existe uma orientação no SIMCC com:

- **título equivalente:** trigramas ≥ 0,80 **ou** cosseno ≥ 0,90;
- **natureza compatível:** IC ↔ Iniciação Científica, Mestrado ↔ Dissertação,
  Doutorado ↔ Tese;
- **ano compatível:** entre o início da bolsa − 1 e o fim previsto + 2.

| `link_method` | Ligações | Bolsas | Orientadores |
|---|---:|---:|---:|
| `lexical` (só trigramas) | 15.700 | 10.313 | 3.299 |
| `both` | 10.556 | 7.455 | 2.966 |
| `semantic` (só embeddings) | 272 | 209 | 196 |
| **Total** | **26.528** | **17.158** | **4.053** |

A maioria das ligações `lexical` tem título praticamente idêntico, mas nota
semântica abaixo de 0,90. Isso acontece porque o título da bolsa costuma
estar em CAIXA ALTA e o da orientação não, e o embedding é sensível a isso
(veja a [calibração](../chatbot/arquitetura.md#calibracao-05102026)).

Em 675 bolsas há **mais de um orientador ligado** (642 com 2, 32 com 3 e 1
com 4). Pode ser coorientação, orientações repetidas no Lattes de pessoas
diferentes, ou projetos "irmãos" com títulos parecidos. A evidência de cada
ligação (título da orientação, ano, notas) fica em
`maria.grant_advisor_links`.

### Cobertura por modalidade

| Modalidade | Bolsas | Pelo bolsista | Pelo orientador | **Com algum pesquisador** |
|---|---:|---:|---:|---:|
| IC | 30.588 | 679 | 13.993 | **14.389 (47%)** |
| Mestrado | 7.344 | 431 | 1.929 | **2.264 (31%)** |
| Doutorado | 3.791 | 518 | 991 | **1.425 (38%)** |
| Mestrado Profissional | 899 | 29 | 245 | **268 (30%)** |
| **Total** | **42.622** | **1.657** | **17.158** | **18.346 (43%)** |

!!! warning "Sem ligação não significa sem produção"
    57% das bolsas não têm nenhum pesquisador ligado no SIMCC. Para elas, a
    produção é **desconhecida**, não zero. O chatbot informa essa cobertura em
    toda resposta sobre resultados.

## Exemplo: Dengue

Com o termo `dengue` e o embedding de `"dengue"`:

| | Valor |
|---|---:|
| Bolsas do tema | 145 (93 `both`, 46 `lexical`, 6 `semantic`) |
| … com pesquisador ligado | 61 |
| Artigos distintos associados | 71 (179 linhas antes de deduplicar) |
| Capítulos distintos | 1 |
| Bolsas / pesquisadores com produção | 36 / 17 |

As 6 bolsas que entraram só pela semântica tratam de chikungunya, arboviroses
e *Aedes*, ou seja, de temas vizinhos.

## Tabela `foment` do SIMCC

O SIMCC tem uma tabela `foment` (413 linhas) com bolsas de produtividade do
CNPq. Ela **não** é usada: a fonte de bolsas deste projeto é
`data/raw/scholarships.parquet`.
