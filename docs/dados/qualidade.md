# Qualidade e cuidados

## A base identifica bolsistas, não bolsas

Cada linha descreve um **bolsista** num projeto e período. **Não há
identificador de bolsa**, e não dá para deduzir quais registros pertencem à
mesma bolsa:

- **O mesmo título de projeto aparece com várias pessoas** (2.013 títulos).
  Pode ser a mesma bolsa com substituição, bolsas diferentes no mesmo projeto
  ou anos diferentes. A base não distingue.
- **A mesma pessoa aparece em vários registros** (7.858 pessoas, até 7
  registros). Pode ser renovação, outra modalidade ou outra bolsa.

Por isso, o projeto **não informa número de bolsas**. As contagens válidas são:

| Pergunta | Como contar |
|---|---|
| Quantos bolsistas? | pessoas distintas: `count(DISTINCT lattes_id)` + registros sem Lattes |
| Quantos registros? | `count(*)` em `maria.holder_records` |
| Quantas bolsas? | **não disponível**: o chatbot explica a distinção |

!!! warning "Correção em 06/10/2026"
    Uma versão anterior derivava "bolsas" agrupando registros do mesmo
    projeto, modalidade, instituição e ciclo. Isso foi removido por não ter
    base nos dados.

## Linhas duplicadas

Há **4.206 linhas** idênticas em todas as colunas (mesmo bolsista, mesmo
projeto, mesmas datas), em 1.957 grupos de até 6 cópias. **2.249 cópias**
foram removidas, e `holder_records.source_rows` guarda quantas linhas cada
registro representa. A soma de `source_rows` é exatamente 45.425, o total de
linhas da planilha. Veja [Limpezas](limpeza.md#4-duplicatas-e-registros-de-bolsistas-ingestbuild).

## Registros e pessoas

- **Uma pessoa pode ter até 7 registros.** São 7.858 pessoas com mais de um.
- **Nunca conte linhas de um JOIN como pessoas ou registros.** Use
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
duas linhas. A avaliação do chatbot pegou esse erro.

## Bolsistas sem Lattes

103 registros não têm Lattes: 101 `not_found` e 2 `foreign_document`. Eles
continuam contando como bolsistas. Cada registro é contado como uma pessoa
diferente, porque não há como saber se são a mesma pessoa.

## Textos

- **111 registros têm resumo vazio ou muito curto,** e 95 não têm
  palavras-chave. A busca temática nesses registros depende do título.
- **O mesmo título e resumo se repetem** entre registros de pessoas e anos
  diferentes.

## Valores incompletos

| Coluna | Problema |
|---|---|
| `major_area` | vazia em 59 registros |
| `subarea` | sempre vazia (descartada) |
| `course` | nunca preenchida em IC |
| CEPs | formatos variados, muitos vazios; não usados |

## Cobertura no SIMCC

Os bolsistas são estudantes e **poucos estão no SIMCC**. A produção
científica é encontrada sobretudo pelo **orientador**, por meio de uma
ligação inferida. Os números estão em [SIMCC](simcc.md).
