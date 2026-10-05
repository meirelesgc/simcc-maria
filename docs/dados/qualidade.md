# Qualidade e cuidados

## Não existe identificador de bolsa

A bolsa é **derivada** (veja a [visão geral](visao-geral.md)). Outras
definições dariam números um pouco diferentes:

| Definição de bolsa | Bolsas | Com >1 bolsista |
|---|---:|---:|
| Título + resumo | 42.181 | 675 |
| + modalidade + instituição | 42.197 | 660 |
| **+ ciclo (data final prevista)**, a adotada | **42.622** | **544** |

## Linhas duplicadas

Há **4.210 linhas** repetidas na planilha, idênticas em todas as colunas
(mesmo bolsista, mesmo projeto, mesmas datas), em grupos de até 6. Elas foram
reduzidas a 1.959 registros, e `grant_holders.source_rows` guarda quantas
linhas cada registro tinha. A soma de `source_rows` é exatamente 45.425, o
total de linhas da planilha.

## Bolsas, vínculos e pessoas

- **Uma bolsa pode ter até 3 bolsistas.** São 544 bolsas com mais de um,
  quase todas de IC.
- **Uma pessoa pode ter até 7 bolsas.** São 7.857 pessoas com mais de uma,
  geralmente IC renovada ou IC seguida de mestrado.
- **Nunca conte linhas de um JOIN como bolsas ou pessoas.** Use
  `count(DISTINCT ...)`.

## Grafias de instituição

A mesma instituição aparece com nomes ou siglas diferentes:

| Sigla | Variantes de nome |
|---|---|
| IFBA | 5 (ex.: "Ifba - Instituto Federal…", "Instituto Federal da Bahia") |
| UCSAL | "Católica **do** Salvador" / "Católica **de** Salvador" |
| UESB | "…**do** Sudoeste da Bahia" / "…Sudoeste da Bahia" |
| UNILAB | "Universidade **da** Integração…" / "Universidade **de** Integração…" |
| UFSBA | 1 registro com a sigla `UFSB` |

O `ingest` unifica isso: `UFSB` vira `UFSBA`, e cada sigla recebe a grafia de
nome mais frequente. Sem essa unificação, agrupar por nome dividia a UESB em
duas linhas (317 + 15 bolsas de doutorado). A avaliação pegou esse erro.

## Bolsistas sem Lattes

103 vínculos não têm Lattes: 101 `not_found` e 2 `foreign_document`. Eles
continuam contando como bolsistas. Cada um é contado como uma pessoa
diferente, porque não há como saber se são a mesma pessoa.

## Textos

- **107 bolsas têm resumo vazio ou muito curto,** e 92 não têm
  palavras-chave. A busca temática nessas bolsas depende do título.
- **Título e resumo são idênticos em projetos repetidos** de anos diferentes.
  Cada ciclo é uma bolsa.

## Valores incompletos

| Coluna | Problema |
|---|---|
| `major_area` | vazia em 56 bolsas |
| `subarea` | sempre vazia (descartada) |
| `course` | frequentemente vazia em IC |
| CEPs | formatos variados, muitos vazios; não usados |

## Cobertura no SIMCC

Os bolsistas são estudantes e **poucos estão no SIMCC**. A produção
científica é encontrada sobretudo pelo **orientador**, por meio de uma
ligação inferida. Os números estão em [SIMCC](simcc.md).
