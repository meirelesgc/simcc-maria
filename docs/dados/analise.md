# Análise da base

Análise exploratória de `data/raw/scholarships.parquet` depois das
[limpezas](limpeza.md). Os números foram calculados com polars sobre
`data/processed/` (`grants` e `grant_holders`) em 06/10/2026.

## Resumo

| | Valor |
|---|---:|
| Registros na planilha | 45.425 |
| Registros distintos (após remover cópias exatas) | 43.176 |
| **Bolsas** | **42.622** |
| Vínculos bolsa–bolsista | 43.174 |
| **Pessoas** (bolsistas distintos) | **32.959** |
| Bolsas com mais de um bolsista | 544 |
| Pessoas com mais de uma bolsa | 7.857 |
| Instituições | 61 |
| Grandes áreas / áreas | 11 / 164 |
| Início das bolsas | mar/2005 a out/2026 |
| Fim previsto mais distante | set/2030 |

## Evolução no tempo

Bolsas por ano de início e modalidade:

| Ano | IC | Mestrado | Doutorado | Mestr. Prof. | Total |
|---:|---:|---:|---:|---:|---:|
| 2005 | 519 | — | — | — | 519 |
| 2006 | 925 | — | — | — | 925 |
| 2007 | 994 | — | — | — | 994 |
| 2008 | 1.012 | — | — | — | 1.012 |
| 2009 | 1.018 | 330 | 109 | — | 1.457 |
| 2010 | 1.082 | 322 | 100 | — | 1.504 |
| 2011 | 1.143 | 256 | 100 | — | 1.499 |
| 2012 | 1.546 | 319 | 136 | 22 | 2.023 |
| 2013 | 2.036 | 405 | 206 | 52 | 2.699 |
| 2014 | 2.340 | 450 | 233 | 63 | 3.086 |
| 2015 | 2.328 | 450 | 150 | 50 | 2.978 |
| 2016 | 1.512 | 445 | 240 | 37 | 2.234 |
| 2017 | 1.402 | 466 | 269 | 37 | 2.174 |
| 2018 | 1.436 | 471 | 264 | 38 | 2.209 |
| 2019 | 1.443 | 462 | 284 | 26 | 2.215 |
| 2020 | 1.391 | 421 | 249 | 52 | 2.113 |
| 2021 | 1.387 | 395 | 241 | 57 | 2.080 |
| 2022 | 1.407 | 386 | 206 | 65 | 2.064 |
| 2023 | 1.442 | 418 | 212 | 84 | 2.156 |
| 2024 | 1.403 | 407 | 205 | 94 | 2.109 |
| 2025 | 1.392 | 462 | 266 | 100 | 2.220 |
| 2026 | 1.430 | 479 | 321 | 122 | 2.352 |

O que a tabela mostra:

- **Mestrado e doutorado aparecem só a partir de 2009,** e o mestrado
  profissional a partir de 2012. Antes disso, a base só tem IC. Uma
  comparação de modalidades que inclua 2005–2008 fica distorcida.
- **A IC teve um pico em 2013–2015** (até 2.340 bolsas por ano) e caiu para
  cerca de 1.400 por ano a partir de 2016.
- **O mestrado profissional cresce desde 2019:** de 26 bolsas para 122 em
  2026.
- **As bolsas de 2026 ainda estão em andamento.** Os números do ano podem
  mudar em uma extração futura.

## Duração e encerramento antecipado

| Modalidade | Duração prevista (mediana) | Encerradas antes do previsto |
|---|---:|---:|
| IC | 12 meses | 134 (0,4%) |
| Mestrado | 23 meses | 993 (13,5%) |
| Mestrado Profissional | 21 meses | 78 (8,7%) |
| Doutorado | 46 meses | 669 (17,6%) |

"Encerrada antes do previsto" significa `end_date < planned_end_date`. A base
não diz o motivo (defesa antecipada, desistência, troca de bolsa…).

## Instituições

As 10 com mais bolsas concentram 88,8% do total, e só a UFBA tem 31%:

| Sigla | Bolsas | | Sigla | Bolsas |
|---|---:|---|---|---:|
| UFBA | 13.345 | | UFRB | 2.301 |
| UESC | 4.835 | | UNIFACS | 1.186 |
| UESB | 4.547 | | EMBRAPA | 1.088 |
| UEFS | 4.318 | | FIOCRUZ | 1.041 |
| UNEB | 4.183 | | IFBA | 1.010 |

## Áreas do conhecimento

Bolsas por grande área e modalidade:

| Grande área | IC | Mestrado | Doutorado | Mestr. Prof. |
|---|---:|---:|---:|---:|
| Ciências da Saúde | 5.294 | 851 | 441 | 95 |
| Ciências Humanas | 4.542 | 1.289 | 592 | 285 |
| Ciências Agrárias | 4.458 | 760 | 499 | 65 |
| Ciências Biológicas | 4.336 | 1.081 | 625 | 39 |
| Ciências Exatas e da Terra | 3.743 | 789 | 286 | 39 |
| Linguística, Letras e Artes | 2.567 | 759 | 419 | 78 |
| Engenharias | 2.488 | 473 | 208 | 35 |
| Ciências Sociais Aplicadas | 2.303 | 706 | 307 | 163 |
| Interdisciplinar | 476 | 442 | 299 | 58 |
| Outros | 221 | 155 | 89 | 27 |
| Tecnologias | 104 | 39 | 26 | 15 |
| *(vazio)* | 56 | — | — | — |

Áreas com mais bolsas: Agronomia (2.519), Educação (2.186), Química (1.583),
Letras (1.560), Saúde Coletiva (1.450), Medicina (1.392), Linguística (1.348),
Interdisciplinar (1.228), História (1.144) e Enfermagem (1.089).

## Textos

| Campo | Observação |
|---|---|
| Título | mediana de 100 caracteres (máx. 250) |
| Resumo | mediana de 1.265 caracteres; 90% têm até 1.496 (máx. 6.565). 107 bolsas têm resumo vazio ou com menos de 20 caracteres |
| Palavras-chave | 4 em 58% dos registros, 3 em 28%, 2 em 14%. 97 registros não têm nenhuma |

São 43.137 palavras-chave distintas (sem acento e em minúsculas). As mais
frequentes: educação (754), memória (527), gênero (471), epidemiologia (431),
cultura (419), políticas públicas (411), saúde (405), literatura (380),
conservação (376) e Bahia (363). A grafia é livre, então "saúde" e "saúde
mental" contam separadamente. É por isso que a busca temática usa texto
completo e embeddings, e não só as palavras-chave.

## Bolsas com mais de um bolsista

| Bolsistas por bolsa | Bolsas |
|---:|---:|
| 1 | 42.078 |
| 2 | 536 |
| 3 | 8 |

- **Quase só IC:** 543 das 544 bolsas são de Iniciação Científica, e uma é de
  mestrado.
- **Onde aparecem:** principalmente na UFBA (120), UESC (75), EMBRAPA (57),
  UNEB (46), UEFS (42) e FIOCRUZ (39).
- **Datas dos bolsistas:** o segundo bolsista começa, em mediana, 123 dias
  depois do primeiro. Em 139 dos 552 pares, os dois começam no mesmo dia.

!!! warning "Substituição ou dois bolsistas ao mesmo tempo?"
    A planilha não encerra a data do primeiro bolsista quando o segundo entra.
    Nos 552 pares, os períodos se sobrepõem. O padrão (mesmo projeto, mesmo
    ciclo, segundo bolsista começando meses depois) sugere **substituição**,
    mas os dados **não permitem confirmar**. Para o chatbot, isso não muda a
    contagem: é uma bolsa, com dois bolsistas.

## Trajetórias dos bolsistas

Uma pessoa pode ter várias bolsas: 7.857 têm mais de uma, até 7.

| Bolsas por pessoa | Pessoas |
|---:|---:|
| 1 | 24.999 |
| 2 | 5.976 |
| 3 | 1.487 |
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
| Mestrado → IC | 5 |
| IC → Mestrado Profissional → Doutorado | 4 |

- **Renovação de IC:** das 23.756 pessoas com IC, 5.846 tiveram duas ou mais
  bolsas de IC.
- **Mais de uma instituição:** 878 pessoas tiveram bolsas em instituições
  diferentes.
- **Casos anômalos:** 5 pessoas aparecem com mestrado antes de IC. Pode ser
  erro de data ou um caso real raro.

## Preenchimento de campos (vínculos bolsa–bolsista)

| Campo | Preenchido | Observação |
|---|---:|---|
| `lattes_id` | 99,8% | 103 vínculos sem Lattes (69 IC, 19 doutorado, 13 mestrado, 2 mestrado profissional) |
| `unit` | 92,9% | |
| `department` | 52,8% | |
| `course` | 27,0% | **Nunca preenchido em IC**; cerca de 96% na pós-graduação |

## Ligação com o SIMCC

Os números de cobertura (bolsistas no SIMCC, ligações com orientadores, por
modalidade) estão em [SIMCC e ligações](simcc.md).
