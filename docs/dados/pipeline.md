# Pipeline: xlsx → csv

```mermaid
flowchart LR
    A[data/raw/raw-data.xlsx] -->|poetry run ingest| B[data/processed/bolsas_pq_dt.csv]
    B -->|poetry run load-db| C[(Postgres · maria.bolsas)]
    C --> D[chatbot]
```

## Convenções

- **`data/raw/`** guarda os arquivos como chegaram e não é editado à mão. Ao
  receber uma extração nova, salve-a ali.
- **`data/processed/`** é gerado por script. Pode ser apagado e regenerado a
  qualquer momento.

## O que o script faz

O script fica em `src/simcc_maria/ingest.py` e:

1. Lê todas as colunas **como texto** (polars + fastexcel), o que preserva os zeros à esquerda do `id_lattes`.
2. Renomeia as colunas para `snake_case` sem acentos (veja o [dicionário](dicionario.md)).
3. Remove a coluna `#` (o número da linha).
4. Remove espaços nas pontas dos valores e converte o texto literal `"NA"` em nulo (ocorre uma vez, em `categoria_nivel`).
5. Converte as datas `dd/mm/aaaa` para ISO (`aaaa-mm-dd`).
6. Converte `qtd_auxilio` e `qtd_bolsa` para inteiro.
7. Cria a coluna `uf` (a sigla) e falha se aparecer um estado sem mapeamento.

## Uso

```bash
poetry run ingest                                   # caminhos padrão
poetry run ingest data/raw/outra.xlsx data/processed/outra.csv
```

## Projetos (CPF → Lattes)

`data/raw/bolsas_projetos.parquet` vem de uma planilha de projetos que trazia o
**CPF** do pesquisador. O CPF foi trocado pelo Lattes ID por meio da API do
SIMCC (`getIdentificadorCNPq`), e **a planilha original foi apagada** (inclusive
do histórico do Git).

| `lattes_status` | Linhas | Significado |
|---|---:|---|
| `ok` | 45.317 | Lattes encontrado |
| `nao_encontrado` | 105 | a API respondeu erro em duas rodadas (91 CPFs distintos) |
| `documento_estrangeiro` | 3 | o documento não era CPF (passaporte) |

Garantias do processo (`src/simcc_maria/resolve_lattes.py`):

- **Uma requisição por CPF distinto:** 32.947 CPFs para 45.425 linhas.
- **Cache local** em `data/cache/` (fora do Git), indexado pelo SHA-256 do
  CPF. O hash **não é anonimização**, porque um CPF pode ser descoberto por
  força bruta. Por isso o cache foi apagado depois da conversão.
- **Parquet (zstd):** 16 MB, contra 70 MB em CSV.
- **CPF e RG digitados em texto livre** (por exemplo, no resumo do projeto)
  foram substituídos por `[CPF removido]` / `[RG removido]`. Foram 3 células.
- **Verificação final:** nenhum CPF da entrada aparece no arquivo, nem como
  célula nem dentro de textos.

!!! warning "Linhas sem Lattes"
    Sem a planilha original, as 108 linhas sem Lattes não podem mais ser
    ligadas a um pesquisador.

## Carga no Postgres

`src/simcc_maria/load_db.py` recria `maria.bolsas` dentro de uma transação:
`CREATE SCHEMA`, `CREATE TABLE`, `COMMENT ON` em cada coluna (com as descrições
de `catalog.py`), `COPY` dos dados, índices e `ANALYZE`.

```bash
poetry run load-db
```

## Lendo o CSV

=== "polars"

    ```python
    from simcc_maria.ingest import read_processed

    df = read_processed()  # tipos corretos: id_lattes texto, datas como Date
    ```

=== "SQL (Postgres)"

    ```sql
    SELECT regiao, sum(qtd_bolsa) AS bolsas
    FROM maria.bolsas
    GROUP BY regiao
    ORDER BY bolsas DESC;
    ```
