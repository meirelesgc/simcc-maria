# Dicionário de dados

## `data/raw/scholarships.parquet`: a planilha de origem

Uma linha por registro de bolsista. Os nomes das colunas foram traduzidos para
o padrão do repositório; o nome original aparece entre parênteses.

| Coluna | Original | Observações |
|---|---|---|
| `lattes_id` | *(cpf_pesquisador)* | Lattes ID do bolsista (16 dígitos). Vazio quando `lattes_status` ≠ `found` |
| `lattes_status` | — | `found` · `not_found` · `foreign_document` |
| `title` | Titulo do Projeto | |
| `abstract` | Resumo do Projeto | Vazio ou curto (< 20 caracteres) em 107 bolsas. CPF/RG digitados foram mascarados |
| `keyword_1`…`keyword_4` | pal_chave1…4 | |
| `start_date` | Data Inicial | `dd/mm/aaaa` na origem |
| `end_date` | Data Final | Término efetivo; anterior ao previsto em 2.062 registros e posterior em 1 |
| `planned_end_date` | Data Final_1 | Término previsto: define o **ciclo** da bolsa |
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

## `maria.grants`: uma linha por bolsa

| Coluna | Tipo | Descrição |
|---|---|---|
| `grant_id` | text PK | Hash de título + resumo normalizados, modalidade, sigla da instituição e data final prevista |
| `title`, `abstract` | text | |
| `keywords` | text[] | União das palavras-chave de todos os registros da bolsa |
| `modality` | text | `undergraduate_research` · `masters` · `professional_masters` · `doctorate` |
| `modality_label` | text | Rótulo original (ex.: `Iniciação Científica - Cotas`) |
| `institution_acronym`, `institution` | text | Uma sigla por instituição e um nome por sigla (a grafia mais frequente) |
| `major_area`, `area` | text | O valor mais frequente entre os registros da bolsa |
| `start_date` | date | Menor início entre os bolsistas |
| `end_date` | date | Maior término efetivo entre os bolsistas |
| `planned_end_date` | date | Término previsto do ciclo |
| `holder_count` | smallint | **Número de bolsistas da bolsa** (1 a 3) |
| `title_norm`, `search_text` | text | Texto normalizado (sem acento, minúsculo) para busca lexical |
| `title_key`, `content_key` | text | Chaves dos embeddings em `maria.embedding_cache` |

## `maria.grant_holders`: uma linha por bolsista de cada bolsa

| Coluna | Tipo | Descrição |
|---|---|---|
| `grant_id`, `holder_seq` | PK | `holder_seq` = ordem de entrada na bolsa |
| `lattes_id` | varchar(16) | Nulo quando o Lattes não foi encontrado |
| `lattes_status` | text | `found` · `not_found` · `foreign_document` |
| `start_date`, `end_date` | date | Período do bolsista na bolsa |
| `unit`, `department`, `course` | text | |
| `source_rows` | int | Quantas linhas idênticas da planilha viraram este registro |

## Objetos derivados

| Objeto | Tipo | Conteúdo |
|---|---|---|
| `maria.grant_researchers` | view | Pesquisadores do SIMCC ligados a cada bolsa: `role` = `holder` (pelo Lattes do bolsista) ou `advisor` (pela orientação) |
| `maria.grant_advisor_links` | tabela | Evidência de cada ligação bolsa → orientador: título da orientação, `lexical_score`, `semantic_score`, `link_method` |
| `maria.productions` | materialized view | Artigos, livros e capítulos do SIMCC com `work_key` (DOI, ou título normalizado + ano) para contar obras distintas |
| `maria.guidance_titles` | tabela | Orientações do SIMCC de IC, mestrado e doutorado (a partir de 2003) |
| `maria.embedding_cache` | tabela | Embeddings `text-embedding-3-small` indexados por hash do texto |
| `maria.search_grants(terms, vec)` | função | Busca temática híbrida em bolsas |
| `maria.search_productions(terms, vec)` | função | Busca temática híbrida em produções |
| `maria.grant_outcomes(terms, vec[, years_after])` | função | Produção temática dos pesquisadores ligados às bolsas do tema, dentro da janela de tempo |
