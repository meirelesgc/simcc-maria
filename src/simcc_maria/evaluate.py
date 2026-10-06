"""Evaluation: questions with known answers.

Expected values come from polars over data/processed (people/record counts) or
from a hand-written reference SQL (theme outcomes, with the terms pinned in the
question). Checks look for the numbers in the FINAL ANSWER TEXT, which is what
the user reads.

Usage:
    poetry run evaluate               # 1 run
    poetry run evaluate --runs 3      # consistency
    poetry run evaluate -k dengue     # only cases whose id contains "dengue"
"""

import argparse
import asyncio
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

import asyncpg
import polars as pl
from rich import box
from rich.console import Console
from rich.table import Table

from simcc_maria.agent import Agent, Answer, _parse_br
from simcc_maria.audit import AuditLog
from simcc_maria.config import ROOT, get_settings
from simcc_maria.db import Database
from simcc_maria.embeddings import Embedder
from simcc_maria.ingest import read_records

console = Console()
NUMBER = re.compile(r"(?<![\w/])(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?(?![\w/])")


def norm(text) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def numbers(text: str) -> set[float]:
    return {_parse_br(t) for t in NUMBER.findall(text)}


# --- checks over the answer text -----------------------------------------------

Check = Callable[[Answer], tuple[bool, str]]


def has_numbers(*expected: int | float) -> Check:
    def check(ans: Answer) -> tuple[bool, str]:
        found = numbers(ans.text)
        missing = [e for e in expected if float(e) not in found]
        return not missing, f"faltou {missing}" if missing else f"citou {list(expected)}"
    return check


def has_groups(expected: dict[tuple[str, ...], int | float]) -> Check:
    """Each group label (any alias) must share a line of the answer with its value."""
    def check(ans: Answer) -> tuple[bool, str]:
        lines = [norm(line) for line in ans.text.splitlines()]
        raw = ans.text.splitlines()
        missing = []
        for aliases, value in expected.items():
            ok = any(
                any(norm(a) in line for a in aliases) and float(value) in numbers(raw[i])
                for i, line in enumerate(lines)
            )
            if not ok:
                missing.append(f"{aliases[0]}={value}")
        return not missing, "faltou " + ", ".join(missing) if missing else f"{len(expected)} grupos"
    return check


def says_unavailable() -> Check:
    phrases = ["nao ha", "nao contem", "nao possui", "nao esta disponivel", "nao e possivel",
               "nao existe", "nao temos", "nao consta", "nao estao disponiveis", "indisponivel"]

    def check(ans: Answer) -> tuple[bool, str]:
        t = norm(ans.text)
        return any(p in t for p in phrases), "declarou indisponível" if any(p in t for p in phrases) else "não declarou"
    return check


def all_of(*checks: Check) -> Check:
    def check(ans: Answer) -> tuple[bool, str]:
        results = [c(ans) for c in checks]
        return all(ok for ok, _ in results), " · ".join(d for _, d in results)
    return check


# --- cases ----------------------------------------------------------------------

@dataclass
class Case:
    id: str
    question: str
    check: Check | None = None
    reference_sql: str | None = None  # expected values computed in the database
    reference_check: Callable[[pl.DataFrame], Check] | None = None
    reference_embed: str | None = None


def _people(df: pl.DataFrame) -> int:
    """Distinct lattes_id plus records without lattes (each counted as a person)."""
    return df["lattes_id"].drop_nulls().n_unique() + df["lattes_id"].null_count()


def says_no_grant_count() -> Check:
    """The answer must say that the base identifies bolsistas, not bolsas."""
    phrases = ["nao identifica", "nao e possivel", "nao permite", "nao ha identificador",
               "nao existe identificador", "nao sabemos", "nao conhecemos", "nao da para",
               "nao informa", "nao contem", "nao possui", "nao registra"]

    def check(ans: Answer) -> tuple[bool, str]:
        t = norm(ans.text)
        ok = "bolsista" in t and any(p in t for p in phrases)
        return ok, "distinguiu bolsas de bolsistas" if ok else "não fez a distinção"
    return check


def build_cases() -> list[Case]:
    r = read_records()
    # "masters" is left out: "Mestrado" is also a substring of "Mestrado Profissional"
    labels = {
        "undergraduate_research": ("Iniciação Científica", "undergraduate_research"),
        "professional_masters": ("Mestrado Profissional", "professional_masters"),
        "doctorate": ("Doutorado", "doctorate"),
    }
    by_mod = {m: _people(r.filter(modality=m)) for m in labels}
    phd = r.filter(modality="doctorate")
    top_phd = (phd.group_by("institution_acronym").agg(pl.col("lattes_id").drop_nulls().n_unique().alias("p"),
                                                       pl.col("lattes_id").null_count().alias("n"))
               .with_columns((pl.col("p") + pl.col("n")).alias("people"))
               .sort(["people", "institution_acronym"], descending=[True, False]).head(5))
    multi = r.drop_nulls("lattes_id").group_by("lattes_id").len().filter(pl.col("len") > 1).height
    ic_then_ms = (
        r.drop_nulls("lattes_id").group_by("lattes_id")
        .agg(pl.col("start_date").filter(pl.col("modality") == "undergraduate_research").min().alias("ic"),
             pl.col("start_date").filter(pl.col("modality") == "masters").min().alias("ms"))
        .filter(pl.col("ic").is_not_null() & pl.col("ms").is_not_null() & (pl.col("ic") < pl.col("ms"))).height
    )
    lexical_dengue = r.filter(
        pl.concat_str([pl.col("title"), pl.col("abstract"), pl.col("keywords").list.join(" ")],
                      separator=" ", ignore_nulls=True)
        .map_elements(norm, return_dtype=pl.String).str.contains(r"(^|[^a-z0-9])dengue")
    )

    return [
        Case("people_by_modality", "Quantos bolsistas (pessoas distintas) existem por modalidade?",
             has_groups({labels[m]: n for m, n in by_mod.items()})),
        Case("records_and_people", "Quantos registros de bolsistas existem no total e quantas pessoas distintas?",
             has_numbers(r.height, _people(r))),
        Case("how_many_grants", "Quantas bolsas existem?", says_no_grant_count()),
        Case("people_multiple_records", "Quantas pessoas têm mais de um registro de bolsa?",
             has_numbers(multi)),
        Case("ic_then_masters", "Quantas pessoas tiveram bolsa de IC e, depois, de mestrado (acadêmico)?",
             has_numbers(ic_then_ms)),
        Case("top5_doctorate", "Quais as 5 instituições com mais bolsistas (pessoas) de doutorado? "
                               "Diga quantos cada uma tem.",
             has_groups({(acr,): n for acr, n in top_phd.select("institution_acronym", "people").iter_rows()})),
        Case("people_start_2020", "Quantas pessoas começaram a receber bolsa em 2020?",
             has_numbers(_people(r.filter(pl.col("start_date").dt.year() == 2020)))),
        Case("dengue_lexical", "Quantos registros de bolsistas e quantas pessoas têm palavras começando por "
                               "'dengue' (incluindo variações como 'dengues') no título, no resumo ou nas "
                               "palavras-chave? Use só busca por palavra, sem semântica.",
             has_numbers(lexical_dengue.height, _people(lexical_dengue))),
        Case("dengue_outcomes_pinned",
             "Considerando a busca temática com o termo 'dengue' e o embedding do texto 'dengue', "
             "quantos artigos, livros e capítulos de livro distintos estão associados aos bolsistas desse tema?",
             reference_embed="dengue",
             reference_sql="""
                SELECT production_type, count(DISTINCT work_key) AS works
                FROM maria.record_outcomes(ARRAY['dengue'], $1::vector)
                GROUP BY 1""",
             reference_check=lambda df: has_groups({
                 {"ARTICLE": ("artigo", "article"), "BOOK": ("livro", "book"),
                  "BOOK_CHAPTER": ("capitulo", "chapter")}[t]: n
                 for t, n in df.iter_rows()
                 # "livro" also matches "capítulo de livro": check chapters/articles only
                 if t != "BOOK"
             })),
        Case("dengue_question",
             "As bolsas contemplam pesquisas na temática Dengue? Se sim, qual o resultado desse fomento? "
             "Ele gerou artigos? livros? capítulos? de quem, quando e quantos"),
        Case("out_of_scope", "Qual foi o valor total, em reais, pago aos bolsistas de doutorado?",
             says_unavailable()),
    ]


# --- run --------------------------------------------------------------------------

async def run(runs: int, only: str | None) -> None:
    s = get_settings()
    cases = [c for c in build_cases() if not only or only in c.id]
    audit = AuditLog("eval")
    db = await Database.connect()
    write_pool = await asyncpg.create_pool(s.asyncpg_dsn, min_size=1, max_size=2, init=Embedder.init_connection)
    embedder = Embedder(write_pool)
    agent = await Agent.create(db, embedder, audit)

    for case in cases:  # reference values from the database
        if case.reference_sql:
            vec = await embedder.embed_one(case.reference_embed)
            ref = (await db.run(case.reference_sql, (vec,))).df
            case.check = case.reference_check(ref)
            audit.write("eval_reference", case=case.id, reference=ref.to_dicts())

    results = []
    try:
        for case in cases:
            for i in range(runs):
                agent.reset()
                with console.status(f"{case.id} ({i + 1}/{runs})"):
                    try:
                        ans = await agent.ask(case.question)
                        if case.check:
                            ok, detail = case.check(ans)
                        else:  # open question: judged by a person; here only sanity
                            ok = bool(ans.text) and not ans.hit_step_limit and not ans.unverified_numbers
                            detail = "revisão manual (sem erro, sem números não conferidos)"
                    except Exception as exc:
                        ans, ok, detail = None, False, f"{type(exc).__name__}: {exc}"
                audit.write("eval_case", case=case.id, run=i + 1, ok=ok, detail=detail)
                results.append((case, i, ok, detail, ans))
    finally:
        await db.close()
        await write_pool.close()

    table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
    for col in ("caso", "ok", "detalhe", "aviso", "passos", "tokens", "s"):
        table.add_column(col, justify="right" if col in ("passos", "tokens", "s") else "left")
    for case, i, ok, detail, ans in results:
        warn = ", ".join(ans.unverified_numbers) if ans and ans.unverified_numbers else ""
        table.add_row(
            case.id + (f" #{i + 1}" if runs > 1 else ""),
            "[green]✔[/green]" if ok else "[red]✘[/red]",
            detail,
            f"[yellow]{warn}[/yellow]",
            str(len(ans.steps)) if ans else "",
            str(ans.usage.total) if ans else "",
            f"{ans.ms / 1000:.0f}" if ans else "",
        )
    console.print(table)
    passed = sum(ok for _, _, ok, _, _ in results)
    tokens = sum(a.usage.total for *_, a in results if a)
    cost = sum(a.usage.cost_usd for *_, a in results if a)
    console.print(f"[bold]{passed}/{len(results)} corretas[/bold] ({passed / len(results):.0%}) · "
                  f"{tokens:,} tokens · US$ {cost:.2f} · {s.llm_model}")
    console.print(f"[dim]log: {audit.path.relative_to(ROOT)}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=1, help="runs per case")
    parser.add_argument("-k", dest="only", help="filter cases by id")
    args = parser.parse_args()
    asyncio.run(run(args.runs, args.only))


if __name__ == "__main__":
    main()
