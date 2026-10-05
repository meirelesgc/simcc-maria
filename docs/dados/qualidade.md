# Qualidade e cuidados

Pontos que afetam análises e respostas do chatbot.

## Pesquisadores com mais de uma linha

Cinco `id_lattes` aparecem duas vezes. Nenhuma das duplicatas é idêntica:

| Pesquisador | O que difere entre as duas linhas |
|---|---|
| Alan Roger dos Santos Silva (UNICAMP) | nível `1D` e nível `2` |
| Túlio Hallak Panzera (UFSJ) | nível `1C` e nível `2` |
| João Nazareno Nonato Quaresma (UFPA) | nível `1C` e nível **vazio** |
| Fernando de Castro Fontainha (UERJ) | `programa_fomento`: "Programas Básicos" e "Não informado" |
| Fernanda Roberta Marciano (UFPI) | `programa_fomento`: "Programas Básicos" e "Não informado" |

Por isso, **contar linhas ≠ contar pessoas** (17.945 contra 17.940). O
chatbot precisa saber se a pergunta é sobre "bolsas" ou sobre "pesquisadores".

## `qtd_bolsa` = 2

Sete linhas têm `qtd_bolsa = 2`, todas de modalidade PQ (níveis `2` e `C`). A
origem não explica o motivo. Somando `qtd_bolsa`, o total é 17.952 bolsas.

## Valores "não informados"

| Coluna | Valor | Linhas |
|---|---|---:|
| `subarea` | `Não informada` | 1.459 |
| `programa_fomento` | `Não informado` | 2 |
| `categoria_nivel` | vazio (na planilha, o texto literal `NA`) | 1 |

## Texto sem acentos

`uf_nome` e `cidade` vêm sem acentos (`Sao Paulo`, `Florianopolis`). As demais
colunas têm acentos. Ao filtrar, normalize o texto: o usuário vai digitar "São
Paulo". Use `uf` (a sigla) sempre que puder.

## Sigla da instituição embutida no nome

`instituicao` traz o nome e a sigla juntos (`Universidade de Brasília UnB`). O
formato da sigla varia: `PUC/PR`, `PUC Minas`, `IF Goiano`, `hcor`. Uma busca
por "UnB" precisa usar `LIKE`/`contains`, e não igualdade. Extrair a sigla com
regras simples gera erros, então ela ainda não foi extraída.

## Formato de datas na origem

As datas vêm como texto `dd/mm/aaaa`, e a data de extração vem como `8/9/2026`.
Tratamos todas como dia/mês, então a extração foi em **8 de setembro de 2026**.
Essa leitura é coerente com as chamadas que começam em 01/08/2026.
