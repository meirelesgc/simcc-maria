"""Replaces CPF with Lattes ID using the SIMCC API.

Usage:
    poetry run resolve-lattes INPUT.xlsx data/raw/scholarships.parquet [--limit N] [--retry-failed]

- Each distinct CPF is requested once.
- Results are cached (data/cache/cpf_lattes.jsonl) keyed by the SHA-256 of the
  CPF, never the plain CPF. Interrupted runs resume where they stopped.
  A CPF hash can be brute-forced: delete the cache after the conversion.
- The output has no CPF: the column becomes `lattes_id` + `lattes_status`, and
  the other columns are renamed to the repository standard (English).
- No CPF is ever printed: errors show only the exception type (httpx messages
  include the URL, which contains the CPF).
"""

import argparse
import asyncio
import hashlib
import json
import re
import time
import warnings
from collections import Counter
from pathlib import Path

import httpx
import polars as pl

from simcc_maria.config import ROOT
from simcc_maria.ingest import SOURCE_COLUMNS

API = "https://simcc.uesc.br/v3/api/getIdentificadorCNPq"
CACHE = ROOT / "data" / "cache" / "cpf_lattes.jsonl"
CPF_COLUMN = "cpf_pesquisador"

CONCURRENCY = 8
TIMEOUT_S = 30
MAX_ATTEMPTS = 3

# lattes_status
OK = "found"
NOT_FOUND = "not_found"  # API answered 500 "Error processing CNPq request" on every attempt
FOREIGN = "foreign_document"  # not a CPF (e.g. passport)
ERROR = "error"  # network/timeout/unexpected answer; redone by --retry-failed


# Personal documents typed in free text (e.g. in the project abstract)
CPF_LABELED = re.compile(r"(\bCPF[\s.:ºo°n]*)\d[\d.\-]{9,13}\d", re.IGNORECASE)
CPF_FORMATTED = re.compile(r"(?<![\d.])\d{3}\.\d{3}\.\d{3}-\d{2}(?![\d.])")
CPF_BARE = re.compile(r"(?<!\d)\d{11}(?!\d)")
RG = re.compile(r"\bR\.?\s?G\.?[\s.:ºo°n]*\d[\d.\-xX]{4,}", re.IGNORECASE)


def cpf_valid(digits: str) -> bool:
    d = [int(x) for x in digits]
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        total = sum(d[i] * (n + 1 - i) for i in range(n))
        if (total * 10) % 11 % 10 != d[n]:
            return False
    return True


def mask_documents(text: str | None) -> str | None:
    """Masks CPF (labeled, or with a valid check digit) and RG."""
    if not text:
        return text
    text = CPF_LABELED.sub(r"\1[CPF removido]", text)  # preceded by "CPF": always
    for pattern in (CPF_FORMATTED, CPF_BARE):  # unlabeled: only with a valid check digit
        text = pattern.sub(
            lambda m: "[CPF removido]" if cpf_valid(re.sub(r"\D", "", m.group())) else m.group(), text
        )
    return RG.sub("[RG removido]", text)


def cpf_key(cpf: str) -> str:
    return hashlib.sha256(cpf.encode()).hexdigest()


def load_cache() -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if CACHE.exists():
        for line in CACHE.read_text().splitlines():
            rec = json.loads(line)
            cache[rec["key"]] = rec  # the last line of each key wins
    return cache


async def lookup(client: httpx.AsyncClient, cpf: str) -> dict:
    status, detail = ERROR, None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = await client.get(API, params={"cpf": cpf, "nomeCompleto": "", "dataNascimento": ""})
            body = r.text.strip()
            if r.status_code == 200 and body.isdigit() and len(body) == 16:
                return {"status": OK, "lattes_id": body, "attempts": attempt}
            if r.status_code == 500 and "Error processing CNPq request" in body:
                status, detail = NOT_FOUND, "500 CNPq"
            else:
                status, detail = ERROR, f"HTTP {r.status_code}"
        except httpx.HTTPError as exc:
            status, detail = ERROR, type(exc).__name__
        await asyncio.sleep(2**attempt)
    return {"status": status, "lattes_id": None, "attempts": MAX_ATTEMPTS, "detail": detail}


async def resolve(cpfs: list[str], retry_failed: bool) -> dict[str, dict]:
    cache = load_cache()
    redo = {ERROR, NOT_FOUND} if retry_failed else {ERROR}
    todo = [c for c in cpfs if cpf_key(c) not in cache or cache[cpf_key(c)]["status"] in redo]
    print(f"{len(cpfs)} distinct CPFs · {len(cpfs) - len(todo)} cached · {len(todo)} to request")

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(CONCURRENCY)
    counts: Counter = Counter()
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        with CACHE.open("a") as f:

            async def worker(cpf: str) -> None:
                async with sem:
                    rec = {"key": cpf_key(cpf), **await lookup(client, cpf)}
                cache[rec["key"]] = rec
                f.write(json.dumps(rec) + "\n")
                f.flush()
                counts[rec["status"]] += 1
                done = sum(counts.values())
                if done % 250 == 0 or done == len(todo):
                    rate = done / (time.monotonic() - start)
                    eta = (len(todo) - done) / rate if rate else 0
                    print(f"  {done}/{len(todo)} · {dict(counts)} · {rate:.1f}/s · ~{eta / 60:.0f} min left", flush=True)

            await asyncio.gather(*(worker(c) for c in todo))
    return cache


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, help="request only the first N distinct CPFs (test)")
    parser.add_argument("--retry-failed", action="store_true", help="also retry not_found")
    args = parser.parse_args()

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="from_arrow", category=FutureWarning)
        df = pl.read_excel(args.input, infer_schema_length=0)

    # Excel may have dropped leading zeros; documents with letters are not CPFs
    doc = pl.col(CPF_COLUMN).str.strip_chars()
    df = df.with_columns(
        pl.when(doc.str.contains(r"^\d+$")).then(doc.str.zfill(11)).otherwise(doc).alias(CPF_COLUMN)
    )
    is_cpf = pl.col(CPF_COLUMN).str.contains(r"^\d{11}$")
    cpfs = df.filter(is_cpf)[CPF_COLUMN].unique(maintain_order=True).to_list()
    if args.limit:
        cpfs = cpfs[: args.limit]

    cache = asyncio.run(resolve(cpfs, args.retry_failed))
    if args.limit:
        return  # test mode: only warms the cache

    keys = df[CPF_COLUMN].map_elements(cpf_key, return_dtype=pl.String)
    df = df.with_columns(
        keys.replace_strict({k: v["lattes_id"] for k, v in cache.items()}, default=None).alias("lattes_id"),
        pl.when(~is_cpf)
        .then(pl.lit(FOREIGN))
        .otherwise(keys.replace_strict({k: v["status"] for k, v in cache.items()}, default=ERROR))
        .alias("lattes_status"),
    )
    out = df.select("lattes_id", "lattes_status", pl.exclude(CPF_COLUMN, "lattes_id", "lattes_status"))
    out = out.rename({k: v for k, v in SOURCE_COLUMNS.items() if k in out.columns})
    text_cols = [c for c in out.columns if c not in ("lattes_id", "lattes_status")]
    masked = out.with_columns(pl.col(text_cols).map_elements(mask_documents, return_dtype=pl.String))
    changed = sum((masked[c] != out[c]).fill_null(False).sum() for c in text_cols)
    print(f"{changed} cells with a personal document masked")
    out = masked
    assert CPF_COLUMN not in out.columns

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix == ".parquet":
        out.write_parquet(args.output, compression="zstd", compression_level=19)
    else:
        out.write_csv(args.output)
    print(f"{out.height} rows -> {args.output}")
    print(out["lattes_status"].value_counts().sort("count", descending=True))


if __name__ == "__main__":
    main()
