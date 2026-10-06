# Dicionário de dados

## `data/raw/scholarships.parquet`: a planilha de origem

Uma linha por registro de bolsista. Os nomes das colunas foram traduzidos para
o padrão do repositório; o nome original aparece entre parênteses.

| Coluna | Original | Observações |
|---|---|---|
| `lattes_id` | *(cpf_pesquisador)* | Lattes ID do bolsista (16 dígitos). Vazio quando `lattes_status` ≠ `found` |
| `lattes_status` | — | `found` · `not_found` · `foreign_document` |
| `title` | Titulo do Projeto | |
| `abstract` | Resumo do Projeto | Vazio ou curto (< 20 caracteres) em 111 registros. CPF/RG digitados foram mascarados |
| `keyword_1`…`keyword_4` | pal_chave1…4 | |
| `start_date` | Data Inicial | `dd/mm/aaaa` na origem |
| `end_date` | Data Final | Término efetivo; anterior ao previsto em 2.062 linhas e posterior em 1 |
| `planned_end_date` | Data Final_1 | Término previsto |
| `institution` | Instituição | |
| `institution_acronym` | Sigla Instituição | 62 siglas na origem; 61 após unificar `UFSB` → `UFSBA` |
| `institution_zip`, `unit_zip`, `department_zip` | Cep … | |
| `unit` | Unidade | |
| `department` | Departamento | |
| `modality` | Modalidade | Rótulo original na origem; vira código no modelo |
| `course` | Nome Curso | |
| `major_area` | Grande Área | |
| `area` | Área | 164 valores |
| `subarea` | Subárea | Sempre vazia: descartada |

## `maria.holder_records`: uma linha por registro de bolsista

Cada linha descreve **um bolsista** (pessoa) em um projeto, numa modalidade,
instituição e período. **Não existe tabela de bolsas**: a origem não
identifica bolsas.

| Coluna | Tipo | Descrição |
|---|---|---|
| `record_id` | text PK | Hash SHA-1 dos valores do registro (estável) |
| `lattes_id` | varchar(16) | Lattes do bolsista; nulo quando não encontrado |
| `lattes_status` | text | `found` · `not_found` · `foreign_document` |
| `title`, `abstract` | text | Projeto do bolsista |
| `keywords` | text[] | As 4 palavras-chave da origem, sem vazios, em ordem alfabética |
| `modality` | text | `undergraduate_research` · `masters` · `professional_masters` · `doctorate` |
| `modality_label` | text | Rótulo original (ex.: `Iniciação Científica - Cotas`) |
| `institution_acronym`, `institution` | text | Uma sigla por instituição e um nome por sigla (a grafia mais frequente) |
| `unit`, `department`, `course` | text | `course` só é preenchido na pós-graduação |
| `major_area`, `area` | text | |
| `start_date`, `end_date`, `planned_end_date` | date | Período do bolsista: início, término efetivo e término previsto |
| `source_rows` | int | Quantas linhas idênticas da planilha viraram este registro |
| `title_norm`, `search_text` | text | Texto normalizado (sem acento, minúsculo) para busca lexical |
| `title_key`, `content_key` | text | Chaves dos embeddings em `maria.embedding_cache` |

Contagens:

- **Bolsistas** (pessoas): `count(DISTINCT lattes_id)` + registros com
  `lattes_id` nulo.
- **Registros:** `count(*)`.

## Objetos derivados

| Objeto | Tipo | Conteúdo |
|---|---|---|
| `maria.record_researchers` | view | Pesquisadores do SIMCC ligados a cada registro: `role` = `holder` (o próprio bolsista, pelo Lattes) ou `advisor` (o orientador, pela orientação) |
| `maria.record_advisor_links` | tabela | Evidência de cada ligação registro → orientador: título da orientação, `lexical_score`, `semantic_score`, `link_method` |
| `maria.productions` | materialized view | Artigos, livros e capítulos do SIMCC com `work_key` (DOI, ou título normalizado + ano) para contar obras distintas |
| `maria.guidance_titles` | tabela | Orientações do SIMCC de IC, mestrado e doutorado (a partir de 2003) |
| `maria.embedding_cache` | tabela | Embeddings `text-embedding-3-small` indexados por hash do texto |
| `maria.search_records(terms, vec)` | função | Busca temática híbrida nos registros de bolsistas |
| `maria.search_productions(terms, vec)` | função | Busca temática híbrida em produções |
| `maria.record_outcomes(terms, vec[, years_after])` | função | Produção temática dos pesquisadores ligados aos registros do tema, dentro da janela de tempo |
