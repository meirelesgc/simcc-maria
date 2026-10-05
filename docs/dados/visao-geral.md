# Visão geral: bolsas PQ/DT do CNPq

## O que é

Um retrato das **bolsas de produtividade do CNPq vigentes** em 08/09/2026,
extraído do BD PICC (o Painel de Investimentos do CNPq). Cada linha é **uma bolsa
concedida a um pesquisador**, com a localização, a área do conhecimento, a
chamada, o nível e o período de vigência.

São duas modalidades:

- **PQ (Produtividade em Pesquisa)**: 17.028 bolsas
- **DT (Produtividade em Desenvolvimento Tecnológico e Extensão Inovadora)**: 917 bolsas

!!! note "É um retrato das bolsas vigentes, não um histórico"
    Todas as bolsas terminam depois da data de extração (o término mais cedo
    é 31/12/2026). A base responde "quem tem bolsa hoje", mas **não** responde
    "quantas bolsas foram concedidas em 2019": as bolsas daquele ano que já
    acabaram não estão aqui.

## Números principais

| Métrica | Valor |
|---|---|
| Linhas (bolsas) | 17.945 |
| Pesquisadores distintos (`id_lattes`) | 17.940 |
| Instituições | 416 |
| Cidades / UFs | 254 / 27 |
| Grandes áreas / áreas / subáreas | 10 / 94 / 361 |
| Chamadas distintas | 19 |
| Data de extração | 08/09/2026 |

## Distribuições

### Por região

| Região | Bolsas | % |
|---|---:|---:|
| Sudeste | 9.650 | 53,8% |
| Sul | 3.576 | 19,9% |
| Nordeste | 2.943 | 16,4% |
| Centro-Oeste | 1.173 | 6,5% |
| Norte | 603 | 3,4% |

Os três estados com mais bolsas são SP (5.000), RJ (2.430) e MG (2.001). Os três
com menos são AP (21), RR (20) e AC (15).

### Por grande área

| Grande área | Bolsas |
|---|---:|
| Ciências Exatas e da Terra | 3.499 |
| Ciências Biológicas | 2.776 |
| Engenharias | 2.290 |
| Ciências Humanas | 2.229 |
| Ciências Agrárias | 2.087 |
| Ciências da Saúde | 1.775 |
| Ciências Sociais Aplicadas | 1.323 |
| Tecnologias *(somente DT)* | 917 |
| Lingüística, Letras e Artes | 699 |
| Outra | 350 |

A grande área **"Tecnologias" é exclusiva da modalidade DT**: toda bolsa DT cai
nela e nenhuma bolsa PQ cai nela.

### Instituições com mais bolsas

| Instituição | Bolsas |
|---|---:|
| Universidade de São Paulo USP | 1.917 |
| Universidade Federal do Rio de Janeiro UFRJ | 853 |
| Universidade Federal de Minas Gerais UFMG | 760 |
| Universidade Estadual Paulista Júlio de Mesquita Filho UNESP | 729 |
| Universidade Federal do Rio Grande do Sul UFRGS | 725 |
| Universidade Estadual de Campinas UNICAMP | 710 |
| Universidade Federal de Santa Catarina UFSC | 499 |
| Universidade de Brasília UnB | 414 |
| Universidade Federal de Pernambuco UFPE | 400 |
| Universidade Federal Fluminense UFF | 367 |

### Por chamada (as principais)

| Chamada | Bolsas | Início |
|---|---:|---|
| Chamada CNPq Nº 18/2024 Bolsas PQ/PQ-Sr/DT | 6.028 | 01/08/2025 |
| Chamada CNPq Nº 23/2025 Bolsas PQ/PQ-Sr/DT | 5.562 | 01/08/2026 |
| Chamada CNPq Nº 09/2023 (PQ/PQ-Sr) | 3.954 | 01/03/2024 |
| Chamada CNPq Nº 09/2022 (PQ) | 1.543 | 01/03/2023 |
| Chamada CNPq Nº 4/2021 (PQ) | 343 | 01/03/2022 |
| Chamada CNPq Nº 04/2023 (DT) | 291 | 01/03/2024 |
| outras 13 chamadas | 224 | 2014–2026 |

### Por nível

O CNPq mudou a escala de níveis a partir das chamadas de 2024. Por isso, a
coluna `categoria_nivel` mistura **duas escalas**:

| Escala | Chamadas | Níveis (do mais alto ao mais baixo) | Bolsas |
|---|---|---|---:|
| Antiga | até 2023 | `1A`, `1B`, `1C`, `1D`, `2` | 6.182 |
| Nova | 18/2024 e 23/2025 | `A`, `B`, `C` | 11.414 |
| Sênior | ambas | `SR` | 348 |

!!! warning "Não compare as escalas diretamente"
    "1A" e "A" não são o mesmo nível. Para perguntas como "quantos
    pesquisadores nível 1A existem", deixe claro (no chatbot também) que a
    resposta cobre apenas as chamadas antigas.

### Vigência

A maioria das bolsas dura **3 anos** (11.007), seguidas pelas de **4 anos**
(4.715) e **5 anos** (2.035). As datas de início vão de 2014 a 2026, mas 97,5%
começaram entre 2023 e 2026.

## Que perguntas esta base responde bem

- **Listagens:** "Quais pesquisadores de Física da UFMG têm bolsa PQ nível A?"
- **Contagens e agrupamentos:** "Quantas bolsas DT existem por região?"
- **Rankings:** "Quais as 10 instituições do Nordeste com mais bolsistas em Ciências da Saúde?"
- **Vencimentos:** "Quantas bolsas terminam em 2027 no RS?"

## Que perguntas ela **não** responde

- Valores em R$: a planilha não traz valores.
- Histórico de concessões, já que só estão as bolsas vigentes.
- Produção científica, orientações ou o currículo do pesquisador. Esses dados
  podem vir da outra aplicação, ligados pelo `id_lattes`.
- Gênero, raça ou idade: não existem colunas para isso.
