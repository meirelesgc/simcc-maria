# Análise da base

Análise exploratória de `data/raw/scholarships.parquet` depois das
[limpezas](limpeza.md). Os números foram calculados com polars sobre
`data/processed/holder_records.parquet` em 06/10/2026.

!!! important "Unidade de análise: o bolsista"
    A base identifica **bolsistas** e seus registros, não **bolsas**. Toda
    contagem abaixo é de **registros** (linhas) ou de **pessoas** (Lattes
    distintos). Nenhum número de bolsas é informado, porque a base não permite
    calculá-lo.

## Resumo

| | Valor |
|---|---:|
| Linhas na planilha | 45.425 |
| Registros de bolsistas (após remover cópias exatas) | 43.176 |
| **Bolsistas** (pessoas distintas) | **32.959** |
| Pessoas com mais de um registro | 7.858 |
| Instituições | 61 |
| Grandes áreas / áreas | 11 / 164 |
| Início dos registros | mar/2005 a out/2026 |
| Fim previsto mais distante | set/2030 |
| Títulos de projeto distintos | 39.854 |

## Evolução no tempo

Registros por ano de início e modalidade, e pessoas distintas que começaram
um registro no ano:

| Ano | IC | Mestrado | Doutorado | Mestr. Prof. | Registros | Pessoas |
|---:|---:|---:|---:|---:|---:|---:|
| 2005 | 531 | — | — | — | 531 | 530 |
| 2006 | 941 | — | — | — | 941 | 933 |
| 2007 | 1.005 | — | — | — | 1.005 | 991 |
| 2008 | 1.026 | — | — | — | 1.026 | 1.014 |
| 2009 | 1.032 | 330 | 109 | — | 1.471 | 1.446 |
| 2010 | 1.111 | 322 | 100 | — | 1.533 | 1.490 |
| 2011 | 1.165 | 256 | 100 | — | 1.521 | 1.485 |
| 2012 | 1.578 | 319 | 136 | 22 | 2.055 | 2.013 |
| 2013 | 2.078 | 405 | 206 | 52 | 2.741 | 2.695 |
| 2014 | 2.405 | 450 | 233 | 63 | 3.151 | 3.083 |
| 2015 | 2.381 | 450 | 150 | 50 | 3.031 | 2.976 |
| 2016 | 1.538 | 445 | 241 | 37 | 2.261 | 2.213 |
| 2017 | 1.417 | 467 | 269 | 37 | 2.190 | 2.182 |
| 2018 | 1.459 | 471 | 264 | 38 | 2.232 | 2.215 |
| 2019 | 1.471 | 462 | 285 | 26 | 2.244 | 2.219 |
| 2020 | 1.402 | 421 | 249 | 52 | 2.124 | 2.101 |
| 2021 | 1.399 | 395 | 241 | 57 | 2.092 | 2.063 |
| 2022 | 1.427 | 386 | 206 | 65 | 2.084 | 2.055 |
| 2023 | 1.479 | 418 | 212 | 84 | 2.193 | 2.146 |
| 2024 | 1.429 | 407 | 205 | 94 | 2.135 | 2.114 |
| 2025 | 1.415 | 462 | 266 | 100 | 2.243 | 2.225 |
| 2026 | 1.450 | 479 | 321 | 122 | 2.372 | 2.336 |

O que a tabela mostra:

- **Mestrado e doutorado aparecem só a partir de 2009,** e o mestrado
  profissional a partir de 2012. Antes disso, a base só tem IC. Uma
  comparação de modalidades que inclua 2005–2008 fica distorcida.
- **A IC teve um pico em 2013–2015** (até 2.405 registros por ano) e caiu para
  cerca de 1.400–1.500 por ano a partir de 2016.
- **O mestrado profissional cresce desde 2019:** de 26 registros para 122 em
  2026.
- **Os registros de 2026 ainda estão em andamento.** Os números do ano podem
  mudar em uma extração futura.

## Duração e encerramento antecipado

| Modalidade | Duração prevista (mediana) | Encerrados antes do previsto |
|---|---:|---:|
| IC | 12 meses | 134 (0,4%) |
| Mestrado | 23 meses | 993 (13,5%) |
| Mestrado Profissional | 21 meses | 78 (8,7%) |
| Doutorado | 46 meses | 669 (17,6%) |

"Encerrado antes do previsto" significa `end_date < planned_end_date` no
registro do bolsista. A base não diz o motivo (defesa antecipada,
desistência, substituição…).

## Instituições

As 10 com mais registros concentram 88,8% do total, e só a UFBA tem 31,2%:

| Sigla | Registros | Bolsistas | | Sigla | Registros | Bolsistas |
|---|---:|---:|---|---|---:|---:|
| UFBA | 13.466 | 10.957 | | UFRB | 2.326 | 1.940 |
| UESC | 4.914 | 3.727 | | UNIFACS | 1.204 | 1.004 |
| UESB | 4.577 | 3.409 | | EMBRAPA | 1.145 | 596 |
| UEFS | 4.361 | 3.199 | | FIOCRUZ | 1.081 | 659 |
| UNEB | 4.229 | 3.427 | | IFBA | 1.035 | 816 |

EMBRAPA (1,9 registro por pessoa) e FIOCRUZ (1,6) têm a maior proporção de
bolsistas com mais de um registro. Nas demais, a proporção fica entre 1,2 e
1,4.

## Áreas do conhecimento

Registros por grande área e modalidade:

| Grande área | IC | Mestrado | Doutorado | Mestr. Prof. |
|---|---:|---:|---:|---:|
| Ciências da Saúde | 5.377 | 851 | 441 | 95 |
| Ciências Humanas | 4.594 | 1.289 | 593 | 285 |
| Ciências Agrárias | 4.571 | 761 | 500 | 65 |
| Ciências Biológicas | 4.420 | 1.081 | 625 | 39 |
| Ciências Exatas e da Terra | 3.807 | 789 | 286 | 39 |
| Linguística, Letras e Artes | 2.596 | 759 | 419 | 78 |
| Engenharias | 2.550 | 473 | 208 | 35 |
| Ciências Sociais Aplicadas | 2.349 | 706 | 307 | 163 |
| Interdisciplinar | 482 | 442 | 299 | 58 |
| Outros | 224 | 155 | 89 | 27 |
| Tecnologias | 110 | 39 | 26 | 15 |
| *(vazio)* | 59 | — | — | — |

Áreas com mais registros: Agronomia (2.587), Educação (2.200), Química
(1.606), Letras (1.571), Saúde Coletiva (1.471), Medicina (1.401), Linguística
(1.362), Interdisciplinar (1.233), História (1.147) e Enfermagem (1.097).

## Textos

| Campo | Observação |
|---|---|
| Título | mediana de 100 caracteres (máx. 250) |
| Resumo | mediana de 1.265 caracteres; 90% têm até 1.496 (máx. 6.565). 111 registros têm resumo vazio ou com menos de 20 caracteres |
| Palavras-chave | 4 em 57% dos registros, 3 em 28%, 2 em 14%. 95 registros não têm nenhuma |

As palavras-chave são de grafia livre. As mais frequentes (sem acento e em
minúsculas): educação, memória, gênero, epidemiologia, cultura, políticas
públicas, saúde, literatura, conservação e Bahia. "Saúde" e "saúde mental"
contam separadamente. É por isso que a busca temática usa texto completo e
embeddings, e não só as palavras-chave.

## Mesmo projeto, várias pessoas

Há 39.854 títulos de projeto distintos (comparando sem diferença de
maiúsculas e espaços). Em **2.013** deles aparece mais de uma pessoa.

Isso **não** diz quantas bolsas existem. Um mesmo projeto pode ter tido
bolsistas em anos diferentes, em modalidades diferentes, em bolsas diferentes
ou numa mesma bolsa com substituição. A base não distingue esses casos.

## Trajetórias dos bolsistas

Uma pessoa pode ter vários registros: 7.858 têm mais de um, até 7.

| Registros por pessoa | Pessoas |
|---:|---:|
| 1 | 24.998 |
| 2 | 5.976 |
| 3 | 1.488 |
| 4 | 327 |
| 5 a 7 | 67 |

Sequência de modalidades de cada pessoa, em ordem cronológica:

| Trajetória | Pessoas |
|---|---:|
| só IC | 21.802 |
| só Mestrado | 5.247 |
| só Doutorado | 2.547 |
| IC → Mestrado | 1.275 |
| só Mestrado Profissional | 775 |
| Mestrado → Doutorado | 514 |
| IC → Doutorado | 418 |
| IC → Mestrado → Doutorado | 154 |
| IC → Mestrado Profissional | 96 |
| Mestrado Profissional → Doutorado | 15 |
| outras combinações | 13 |

- **Mais de um registro de IC:** das 23.756 pessoas com IC, 5.846 têm dois ou
  mais.
- **Mais de uma instituição:** 878 pessoas aparecem em instituições
  diferentes.
- **Casos anômalos:** 5 pessoas aparecem com mestrado antes de IC, e há outras
  combinações raras. Pode ser erro de data ou um caso real.

## Preenchimento de campos

| Campo | Preenchido | Observação |
|---|---:|---|
| `lattes_id` | 99,8% | 103 registros sem Lattes (69 IC, 19 doutorado, 13 mestrado, 2 mestrado profissional) |
| `unit` | 92,9% | |
| `department` | 52,8% | |
| `course` | 27,0% | **Nunca preenchido em IC**; cerca de 96% na pós-graduação |

## Ligação com o SIMCC

Os números de cobertura (bolsistas no SIMCC, ligações com orientadores, por
modalidade) estão em [SIMCC e ligações](simcc.md).
