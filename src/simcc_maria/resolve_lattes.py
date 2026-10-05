"""Substitui CPF por Lattes ID usando a API do SIMCC.

Uso:
    poetry run resolve-lattes ENTRADA.xlsx SAIDA.parquet [--limit N] [--retry-failed]

- Cada CPF distinto é consultado uma única vez.
- Os resultados ficam em cache (data/cache/cpf_lattes.jsonl), indexados pelo
  SHA-256 do CPF, nunca pelo CPF em texto puro. Execuções interrompidas
  retomam de onde pararam.
- A saída não contém CPF: a coluna vira `lattes_id` + `lattes_status`.
- Nenhum CPF é impresso: erros mostram só o tipo da exceção (a mensagem do
  httpx inclui a URL, que contém o CPF).
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

API = "https://simcc.uesc.br/v3/api/getIdentificadorCNPq"
CACHE = ROOT / "data" / "cache" / "cpf_lattes.jsonl"
CPF_COLUMN = "cpf_pesquisador"

CONCURRENCY = 8
TIMEOUT_S = 30
MAX_ATTEMPTS = 3

# lattes_status
OK = "ok"
NOT_FOUND = "nao_encontrado"  # API respondeu 500 "Error processing CNPq request" em todas as tentativas
FOREIGN = "documento_estrangeiro"  # não é CPF (ex.: passaporte)
ERROR = "erro"  # falha de rede/timeout/resposta inesperada; refeito com --retry-failed


# Documentos pessoais digitados em texto livre (ex.: no resumo do projeto)
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
    """Mascara CPF (rotulado, ou com dígito verificador válido) e RG."""
    if not text:
        return text
    text = CPF_LABELED.sub(r"\1[CPF removido]", text)  # precedido de "CPF": sempre
    for pattern in (CPF_FORMATTED, CPF_BARE):  # sem rótulo: só se o dígito verificador bater
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
            cache[rec["key"]] = rec  # a última linha de cada chave prevalece
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
    print(f"{len(cpfs)} CPFs distintos · {len(cpfs) - len(todo)} no cache · {len(todo)} a consultar")

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
                    print(f"  {done}/{len(todo)} · {dict(counts)} · {rate:.1f}/s · faltam ~{eta / 60:.0f} min", flush=True)

            await asyncio.gather(*(worker(c) for c in todo))
    return cache


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("entrada", type=Path)
    parser.add_argument("saida", type=Path)
    parser.add_argument("--limit", type=int, help="consulta só os N primeiros CPFs distintos (teste)")
    parser.add_argument("--retry-failed", action="store_true", help="refaz também os nao_encontrado")
    args = parser.parse_args()

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="from_arrow", category=FutureWarning)
        df = pl.read_excel(args.entrada, infer_schema_length=0)

    # O Excel pode ter perdido zeros à esquerda; documentos com letras não são CPF
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
        return  # modo teste: só aquece o cache

    keys = df[CPF_COLUMN].map_elements(cpf_key, return_dtype=pl.String)
    df = df.with_columns(
        keys.replace_strict({k: v["lattes_id"] for k, v in cache.items()}, default=None).alias("lattes_id"),
        pl.when(~is_cpf)
        .then(pl.lit(FOREIGN))
        .otherwise(keys.replace_strict({k: v["status"] for k, v in cache.items()}, default=ERROR))
        .alias("lattes_status"),
    )
    out = df.select("lattes_id", "lattes_status", pl.exclude(CPF_COLUMN, "lattes_id", "lattes_status"))
    text_cols = [c for c in out.columns if c not in ("lattes_id", "lattes_status")]
    masked = out.with_columns(pl.col(text_cols).map_elements(mask_documents, return_dtype=pl.String))
    changed = sum((masked[c] != out[c]).fill_null(False).sum() for c in text_cols)
    print(f"{changed} células com documento pessoal mascarado")
    out = masked
    assert CPF_COLUMN not in out.columns

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    if args.saida.suffix == ".parquet":
        out.write_parquet(args.saida, compression="zstd", compression_level=19)
    else:
        out.write_csv(args.saida)
    print(f"{out.height} linhas -> {args.saida}")
    print(out["lattes_status"].value_counts().sort("count", descending=True))


if __name__ == "__main__":
    main()
