# Visão geral: bolsas por cotas

## O que é

Um registro de **bolsas por cotas** de Iniciação Científica, Mestrado,
Mestrado Profissional e Doutorado, concedidas a partir de 2005, quase todas em
instituições da Bahia. Cada linha da planilha é o registro de um **bolsista**
(estudante) em um **projeto**, com título, resumo, palavras-chave, instituição,
área e datas.

O arquivo é `data/raw/scholarships.parquet`. O CPF da origem foi trocado pelo
Lattes ID (veja o relatório no `README.md` do repositório e o
[pipeline](pipeline.md)).

!!! important "Uma bolsa pode ter mais de um bolsista"
    A planilha não tem identificador de bolsa. Definimos **bolsa** (`grant`) como:

    **mesmo projeto** (título + resumo normalizados) + **modalidade** +
    **instituição** + **ciclo** (data final prevista)

    Quando um aluno é substituído no meio do ciclo, a bolsa continua sendo a
    mesma e passa a ter dois bolsistas. Uma renovação para o ciclo seguinte é
    outra bolsa.

## Números principais

| Métrica | Valor |
|---|---:|
| Linhas na planilha | 45.425 |
| **Bolsas** (`maria.grants`) | **42.622** |
| Bolsas com mais de um bolsista | 544 (536 com 2 e 8 com 3) |
| Pares bolsa–bolsista (`maria.grant_holders`) | 43.174 |
| **Pessoas distintas** (bolsistas) | **32.959** |
| Pessoas com mais de uma bolsa | 7.857 (até 7 bolsas) |
| Instituições (siglas) | 61 |
| Áreas | 164, em 11 grandes áreas |
| Período (início) | 2005 a 2026 |

!!! warning "Três contagens diferentes"
    - **Bolsas:** 42.622.
    - **Vínculos bolsa–bolsista:** 43.174.
    - **Pessoas:** 32.959.

    Elas diferem porque uma bolsa pode ter vários bolsistas e uma pessoa pode
    ter várias bolsas ao longo dos anos. O chatbot conta cada uma de um jeito
    diferente (veja as regras na [arquitetura](../chatbot/arquitetura.md)).

## Por modalidade

| `modality` | Rótulo original | Bolsas | Com >1 bolsista | Vínculos | Pessoas |
|---|---|---:|---:|---:|---:|
| `undergraduate_research` | Iniciação Científica - Cotas | 30.588 | 543 | 31.139 | 23.825 |
| `masters` | Mestrado - Cotas | 7.344 | 1 | 7.345 | 7.211 |
| `doctorate` | Doutorado - Cotas | 3.791 | 0 | 3.791 | 3.672 |
| `professional_masters` | Mestrado Profissional - Cotas | 899 | 0 | 899 | 895 |

Bolsas com mais de um bolsista são, na prática, um fenômeno da **Iniciação
Científica**: são substituições de aluno dentro do mesmo ciclo.

## Instituições com mais bolsas

| Sigla | Bolsas |
|---|---:|
| UFBA | 13.345 |
| UESC | 4.835 |
| UESB | 4.547 |
| UEFS | 4.318 |
| UNEB | 4.183 |
| UFRB | 2.301 |
| UNIFACS | 1.186 |
| EMBRAPA | 1.088 |
| FIOCRUZ | 1.041 |
| IFBA | 1.010 |

## Por grande área

| Grande área | Bolsas |
|---|---:|
| Ciências Humanas | 6.708 |
| Ciências da Saúde | 6.681 |
| Ciências Biológicas | 6.081 |
| Ciências Agrárias | 5.782 |
| Ciências Exatas e da Terra | 4.857 |
| Linguística, Letras e Artes | 3.823 |
| Ciências Sociais Aplicadas | 3.479 |
| Engenharias | 3.204 |
| Interdisciplinar | 1.275 |
| Outros | 492 |
| Tecnologias | 184 |
| *(vazio)* | 56 |

## Duração

A maioria das bolsas tem ciclo de **12 meses** (27.539), típico da IC. Depois
vêm os ciclos de 24 meses (mestrado) e 48 meses (doutorado). Em 1.874 bolsas,
o término efetivo (`end_date`) é anterior ao previsto (`planned_end_date`).

## Ligação com o SIMCC

Os bolsistas são em sua maioria **estudantes**, e poucos estão cadastrados no
SIMCC. Para chegar à produção científica, a bolsa também é ligada ao
**orientador**, pela orientação registrada no SIMCC. Os detalhes e a cobertura
estão em [SIMCC](simcc.md).
