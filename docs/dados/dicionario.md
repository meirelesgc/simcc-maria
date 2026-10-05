# Dicionário de dados

Arquivo: `data/processed/bolsas_pq_dt.csv`, em UTF-8, separado por vírgula, com
uma linha por bolsa e 22 colunas.

| Coluna | Coluna original | Tipo | Exemplo | Observações |
|---|---|---|---|---|
| `id_lattes` | `# Id Lattes` | texto (16 dígitos) | `0000325690951570` | ID do currículo Lattes. **Leia como texto**, porque tem zeros à esquerda. É a chave para ligar com outras fontes. |
| `nome_beneficiario` | `# Nome Beneficiário` | texto | `Ana Luiza Coelho Netto` | Há homônimos: 17.935 nomes para 17.940 IDs. Use `id_lattes` para identificar a pessoa. |
| `pais` | `# Nome País` | texto | `Brasil` | Sempre "Brasil". |
| `regiao` | `# Nome Região` | categoria (5) | `Sudeste` | |
| `uf` | *(derivada)* | sigla (27) | `RJ` | Criada a partir de `uf_nome`. |
| `uf_nome` | `# Nome UF` | texto (27) | `Sao Paulo` | **Sem acentos** na origem. |
| `cidade` | `# Nome Cidade` | texto (254) | `Sao Carlos` | **Sem acentos** na origem. É a cidade da instituição. |
| `linha_fomento` | `# Linha Fomento` | texto | `BOLSAS DE FORMAÇÃO E DE PESQUISADORES` | Valor constante. |
| `grande_area` | `# Nome Grande Área` | categoria (10) | `Engenharias` | "Tecnologias" só aparece em bolsas DT. Existe a categoria "Outra" (350 bolsas). |
| `area` | `# Nome Área` | texto (94) | `Geociências` | |
| `subarea` | `# Nome Sub-área` | texto (361) | `Geografia Física` | 1.459 linhas trazem "Não informada". |
| `modalidade_cod` | `# Cod Modalidade` | `PQ` \| `DT` | `PQ` | |
| `modalidade` | `# Nome Modalidade` | texto (2) | `Produtividade em Pesquisa` | Nome por extenso de `modalidade_cod`. |
| `chamada` | `# Título Chamada` | texto (19) | `Chamada CNPq Nº 18/2024 Bolsas PQ/PQ-Sr/DT` | O edital que concedeu a bolsa. |
| `categoria_nivel` | `# Cod Categoria Nível` | categoria | `C` | Mistura duas escalas (veja a [visão geral](visao-geral.md#por-nivel)). Tem 1 valor vazio (`NA` na origem). |
| `programa_fomento` | `# Nome Programa Fomento` | texto (15) | `Programas Básicos` | 94% são "Programas Básicos". Em DT, indica o programa tecnológico. |
| `instituicao` | `# Nome Instituto` | texto (416) | `Universidade Federal de São Carlos UFSCAR` | Nome e sigla vêm **na mesma string**, e a sigla nem sempre é a última palavra (ex.: `PUC Minas`). |
| `data_inicio` | `# Data Início Processo` | data ISO | `2025-08-01` | Na origem: `dd/mm/aaaa`. |
| `data_termino` | `# Data Término Processo` | data ISO | `2028-07-31` | |
| `data_extracao` | `# Data Extração BD PICC` | data ISO | `2026-09-08` | Valor constante. Na origem: `8/9/2026`. |
| `qtd_auxilio` | `QUANTAUXILIO` | inteiro | `0` | Sempre 0. |
| `qtd_bolsa` | `QUANTBOLSA` | inteiro | `1` | 1, exceto em 7 linhas com 2. Para contar bolsas, some esta coluna; para contar pessoas, conte `id_lattes` distintos. |

A coluna `#` da planilha (o número da linha, formatado como `1.000`) foi
descartada.

## Colunas constantes

`pais`, `linha_fomento`, `data_extracao` e `qtd_auxilio` têm um único valor
nesta planilha. Elas foram mantidas porque podem variar em extrações futuras ou
em outras fontes.
