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
