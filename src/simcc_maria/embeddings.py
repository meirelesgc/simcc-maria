"""OpenAI embeddings cached in Postgres (maria.embedding_cache).

The cache is keyed by sha256(model + text): a text is never embedded twice,
interrupted runs resume where they stopped, and the vectors never need to fit
in Python memory all at once (tables join the cache by key).
"""

import asyncio
import hashlib

import asyncpg
import numpy as np
from openai import AsyncOpenAI
from pgvector.asyncpg import register_vector

from simcc_maria.config import get_settings

MAX_CHARS = 8000  # ~2-3k tokens in Portuguese; the model accepts 8191 tokens
BATCH_CHARS = 400_000  # keeps each request well under the 300k tokens limit
BATCH_ITEMS = 500
CONCURRENCY = 16  # the API takes ~10-20 s per batch; rate limits are far above this

CACHE_DDL = """
CREATE SCHEMA IF NOT EXISTS maria;
CREATE TABLE IF NOT EXISTS maria.embedding_cache (
  key text PRIMARY KEY,
  model text NOT NULL,
  embedding vector(1536) NOT NULL
);
"""


def prepare_text(text: str | None) -> str:
    return (text or "").strip()[:MAX_CHARS] or "-"


def text_key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\x1f{prepare_text(text)}".encode()).hexdigest()


class Embedder:
    def __init__(self, pool: asyncpg.Pool):
        s = get_settings()
        self.pool = pool
        self.model = s.embedding_model
        self.client = AsyncOpenAI(api_key=s.openai_api_key.get_secret_value(), timeout=120, max_retries=2)

    @staticmethod
    async def init_connection(con: asyncpg.Connection) -> None:
        await register_vector(con)

    def key(self, text: str | None) -> str:
        return text_key(self.model, text)

    async def _request(self, texts: list[str]) -> list[list[float]]:
        for attempt in range(5):
            try:
                resp = await self.client.embeddings.create(model=self.model, input=texts)
                return [d.embedding for d in resp.data]
            except Exception:
                if attempt == 4:
                    raise
                await asyncio.sleep(2 ** (attempt + 1))
        raise RuntimeError("unreachable")

    async def ensure(self, texts: list[str | None], label: str = "") -> list[str]:
        """Makes sure every text has a cached embedding; returns the cache keys."""
        prepared = {self.key(t): prepare_text(t) for t in texts}
        async with self.pool.acquire() as con:
            have = {
                r["key"]
                for r in await con.fetch(
                    "SELECT key FROM maria.embedding_cache WHERE key = ANY($1::text[])", list(prepared)
                )
            }
        todo = [(k, t) for k, t in prepared.items() if k not in have]
        if label:
            print(f"  {label}: {len(prepared)} distinct texts · {len(have)} cached · {len(todo)} to embed", flush=True)

        batches, current, size = [], [], 0
        for k, t in todo:
            if current and (size + len(t) > BATCH_CHARS or len(current) >= BATCH_ITEMS):
                batches.append(current)
                current, size = [], 0
            current.append((k, t))
            size += len(t)
        if current:
            batches.append(current)

        sem = asyncio.Semaphore(CONCURRENCY)
        done = 0

        async def run(batch):
            nonlocal done
            async with sem:
                vecs = await self._request([t for _, t in batch])
            records = [(k, self.model, np.asarray(v, dtype=np.float32)) for (k, _), v in zip(batch, vecs)]
            async with self.pool.acquire() as con:
                await con.executemany(
                    "INSERT INTO maria.embedding_cache (key, model, embedding) VALUES ($1, $2, $3) "
                    "ON CONFLICT (key) DO NOTHING",
                    records,
                )
            done += 1
            if label and (done % 25 == 0 or done == len(batches)):
                print(f"    {done}/{len(batches)} requests", flush=True)

        await asyncio.gather(*(run(b) for b in batches))
        return [self.key(t) for t in texts]

    async def embed_one(self, text: str) -> np.ndarray:
        (key,) = await self.ensure([text])
        async with self.pool.acquire() as con:
            return await con.fetchval("SELECT embedding FROM maria.embedding_cache WHERE key = $1", key)
