# SIMCC e ligações

O SIMCC é a fonte da **produção científica** (artigos, livros, capítulos) e
das **orientações** que ligam os bolsistas aos pesquisadores.

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

## Ligação registro de bolsista → pesquisador

```mermaid
flowchart LR
    H[maria.holder_records] -->|lattes_id| R[(public.researcher)]
    H -->|título do projeto ≈ título da orientação<br/>lexical OU semântico| GT[maria.guidance_titles]
    GT -->|orientador| R
    R --> P[maria.productions]
```

### Pelo próprio bolsista (`role = 'holder'`)

Os bolsistas são estudantes, e poucos estão no SIMCC:

| | Valor |
|---|---:|
| Bolsistas (pessoas) que estão no SIMCC | 1.235 de 32.959 (3,7%) |
| Registros desses bolsistas | 1.659 |

### Pelo orientador (`role = 'advisor'`)

Um registro é ligado a um orientador quando existe uma orientação no SIMCC
com:

- **título equivalente ao do projeto:** trigramas ≥ 0,80 **ou** cosseno ≥ 0,90;
- **natureza compatível:** IC ↔ Iniciação Científica, Mestrado ↔ Dissertação,
  Doutorado ↔ Tese;
- **ano compatível:** entre o início do registro − 1 e o fim previsto + 2.

| `link_method` | Ligações | Registros | Orientadores |
|---|---:|---:|---:|
| `lexical` (só trigramas) | 15.986 | 10.459 | 3.301 |
| `both` | 10.742 | 7.557 | 2.966 |
| `semantic` (só embeddings) | 275 | 212 | 197 |
| **Total** | **27.003** | **17.396** | **4.053** |

A maioria das ligações `lexical` tem título praticamente idêntico, mas nota
semântica abaixo de 0,90. Isso acontece porque o título do projeto costuma
estar em CAIXA ALTA e o da orientação não, e o embedding é sensível a isso
(veja a [calibração](../chatbot/arquitetura.md#calibracao-05102026)).

Em 685 registros há **mais de um orientador ligado** (650 com 2, 34 com 3 e 1
com 4). Pode ser coorientação, orientações repetidas no Lattes de pessoas
diferentes, ou projetos "irmãos" com títulos parecidos. A evidência de cada
ligação (título da orientação, ano, notas) fica em
`maria.record_advisor_links`.

### Cobertura por modalidade

| Modalidade | Registros | Pelo bolsista | Pelo orientador | **Com algum pesquisador** | Pessoas cobertas |
|---|---:|---:|---:|---:|---:|
| IC | 31.139 | 680 | 14.230 | **14.627 (47%)** | 11.995 |
| Mestrado | 7.345 | 431 | 1.929 | **2.264 (31%)** | 2.234 |
| Doutorado | 3.793 | 519 | 992 | **1.426 (38%)** | 1.383 |
| Mestrado Profissional | 899 | 29 | 245 | **268 (30%)** | 267 |
| **Total** | **43.176** | **1.659** | **17.396** | **18.585 (43%)** | **15.248** |

"Pessoas cobertas" são bolsistas com Lattes que têm ao menos um registro
ligado a algum pesquisador. A soma por modalidade passa do total porque uma
pessoa pode ter registros em mais de uma modalidade.

!!! warning "Sem ligação não significa sem produção"
    57% dos registros não têm nenhum pesquisador ligado no SIMCC. Para eles, a
    produção é **desconhecida**, não zero. O chatbot informa essa cobertura em
    toda resposta sobre resultados.

## Exemplo: Dengue

Com o termo `dengue` e o embedding de `"dengue"`:

| | Valor |
|---|---:|
| Registros de bolsistas do tema | 146 (94 `both`, 46 `lexical`, 6 `semantic`) |
| Bolsistas (pessoas) do tema | 131 |
| … registros com pesquisador ligado | 61 (57 pessoas) |
| Artigos distintos associados | 71 (179 linhas antes de deduplicar) |
| Capítulos distintos | 1 |
| Registros / bolsistas / pesquisadores com produção | 36 / 33 / 17 |

Os 6 registros que entraram só pela semântica tratam de chikungunya,
arboviroses e *Aedes*, ou seja, de temas vizinhos.

## Tabela `foment` do SIMCC

O SIMCC tem uma tabela `foment` (413 linhas) com bolsas de produtividade do
CNPq. Ela **não** é usada: a fonte de bolsistas deste projeto é
`data/raw/scholarships.parquet`.
