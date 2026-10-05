"""Read-only Postgres access for the chatbot."""

import time
from dataclasses import dataclass

import asyncpg
import polars as pl

from simcc_maria.config import get_settings
from simcc_maria.embeddings import Embedder


@dataclass
class QueryResult:
    df: pl.DataFrame
    truncated: bool  # the result had more rows than sql_max_rows
    ms: int


class Database:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls) -> "Database":
        settings = get_settings()
        pool = await asyncpg.create_pool(
            settings.asyncpg_dsn,
            min_size=1,
            max_size=4,
            init=Embedder.init_connection,
            server_settings={
                "search_path": "maria,public",
                "default_transaction_read_only": "on",
                "application_name": "simcc-maria",
                "client_connection_check_interval": "10s",
            },
        )
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    async def run(self, sql: str, args: tuple = ()) -> QueryResult:
        """Runs a query in a READ ONLY transaction, with timeout and row limit."""
        settings = get_settings()
        start = time.perf_counter()
        async with self.pool.acquire() as con:
            async with con.transaction(readonly=True):
                await con.execute(f"SET LOCAL statement_timeout = {settings.sql_timeout_s * 1000}")
                # prepare() rejects multiple statements in one string
                stmt = await con.prepare(sql)
                columns = [a.name for a in stmt.get_attributes()]
                cursor = await stmt.cursor(*args)
                records = await cursor.fetch(settings.sql_max_rows + 1)

        truncated = len(records) > settings.sql_max_rows
        records = records[: settings.sql_max_rows]
        df = _to_polars(columns, records)
        return QueryResult(df=df, truncated=truncated, ms=int((time.perf_counter() - start) * 1000))

    async def fetch_values(self, sql: str) -> list:
        async with self.pool.acquire() as con:
            return [r[0] for r in await con.fetch(sql)]


def _to_polars(columns: list[str], records: list[asyncpg.Record]) -> pl.DataFrame:
    # Repeated column names (e.g. two "count") would break the DataFrame
    seen: dict[str, int] = {}
    unique = []
    for c in columns:
        seen[c] = seen.get(c, 0) + 1
        unique.append(c if seen[c] == 1 else f"{c}_{seen[c]}")

    if not records:
        return pl.DataFrame(schema={c: pl.String for c in unique})
    data = {c: [r[i] for r in records] for i, c in enumerate(unique)}
    return pl.DataFrame(data, strict=False)
