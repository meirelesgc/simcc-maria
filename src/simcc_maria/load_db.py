"""Carrega o CSV processado na tabela maria.bolsas (recria a tabela).

Uso: poetry run load-db
"""

import asyncio

import asyncpg

from simcc_maria.catalog import COLUMNS, TABLE, TABLE_DESCRIPTION
from simcc_maria.config import get_settings
from simcc_maria.ingest import read_processed

INDEXES = ["id_lattes", "uf", "regiao", "grande_area", "area", "modalidade_cod", "categoria_nivel"]


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def ddl() -> list[str]:
    cols = ",\n  ".join(f"{name} {pg_type}" for name, (pg_type, _) in COLUMNS.items())
    stmts = [
        "CREATE SCHEMA IF NOT EXISTS maria",
        f"DROP TABLE IF EXISTS {TABLE}",
        f"CREATE TABLE {TABLE} (\n  id serial PRIMARY KEY,\n  {cols}\n)",
        f"COMMENT ON TABLE {TABLE} IS {_quote(TABLE_DESCRIPTION)}",
    ]
    stmts += [
        f"COMMENT ON COLUMN {TABLE}.{name} IS {_quote(desc)}"
        for name, (_, desc) in COLUMNS.items()
    ]
    return stmts


async def load() -> int:
    settings = get_settings()
    df = read_processed()
    con = await asyncpg.connect(settings.asyncpg_dsn)
    try:
        async with con.transaction():
            for stmt in ddl():
                await con.execute(stmt)
            await con.copy_records_to_table(
                "bolsas",
                schema_name="maria",
                columns=list(COLUMNS),
                records=df.select(list(COLUMNS)).iter_rows(),
            )
            for col in INDEXES:
                await con.execute(f"CREATE INDEX ON {TABLE} ({col})")
        await con.execute(f"ANALYZE {TABLE}")
        return await con.fetchval(f"SELECT count(*) FROM {TABLE}")
    finally:
        await con.close()


def main() -> None:
    print(f"{asyncio.run(load())} linhas carregadas em {TABLE}")


if __name__ == "__main__":
    main()
