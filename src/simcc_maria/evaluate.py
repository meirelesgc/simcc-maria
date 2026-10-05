"""Avaliação: perguntas com resposta conhecida, calculada em polars a partir do CSV.

Uso:
    poetry run evaluate                 # 1 rodada
    poetry run evaluate --runs 3        # mede consistência (mesma pergunta, 3 vezes)
    poetry run evaluate -k nivel        # só casos cujo id contém "nivel"
    LLM_MODEL_SUMMARY=openai:gpt-5.4-mini poetry run evaluate   # compara modelos
"""

import argparse
import asyncio
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

import polars as pl
from rich import box
from rich.console import Console
from rich.table import Table

from simcc_maria.audit import AuditLog
from simcc_maria.config import ROOT, get_settings
from simcc_maria.db import Database
from simcc_maria.ingest import read_processed
from simcc_maria.pipeline import Answer, Pipeline

console = Console()
D = read_processed()

PESSOAS = pl.col("id_lattes").n_unique()
BOLSAS = pl.col("qtd_bolsa").sum()


def norm(text) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


# --- verificações -------------------------------------------------------------

Check = Callable[[Answer], tuple[bool, str]]


def _numbers(row) -> set[float]:
    out = set()
    for v in row:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.add(float(v))
        else:
            try:
                out.add(float(v))
            except (TypeError, ValueError):
                pass
    return out


def scalar(expected: int | float) -> Check:
    def check(ans: Answer) -> tuple[bool, str]:
        if ans.df is None or ans.df.is_empty():
            return False, "sem resultado"
        found = set().union(*(_numbers(r) for r in ans.df.iter_rows()))
        return float(expected) in found, f"esperado {expected}"
    return check


def groups(expected: dict[tuple[str, ...], int | float]) -> Check:
    """Cada grupo (com apelidos aceitos) precisa aparecer com o valor esperado."""
    def label_match(cell, aliases) -> bool:
        c = norm(cell)
        return any(c == norm(a) or (len(a) > 3 and norm(a) in c) for a in aliases)

    def check(ans: Answer) -> tuple[bool, str]:
        if ans.df is None or ans.df.is_empty():
            return False, "sem resultado"
        missing = []
        for aliases, value in expected.items():
            ok = any(
                any(label_match(v, aliases) for v in row if isinstance(v, str))
                and float(value) in _numbers(row)
                for row in ans.df.iter_rows()
            )
            if not ok:
                missing.append(f"{aliases[0]}={value}")
        return not missing, "faltou " + ", ".join(missing) if missing else f"{len(expected)} grupos"
    return check


def names(expected: set[str]) -> Check:
    def check(ans: Answer) -> tuple[bool, str]:
        if ans.df is None or ans.df.is_empty():
            return False, "sem resultado"
        want = {norm(n) for n in expected}
        best = max(
            ({norm(v) for v in ans.df[c].to_list()} for c in ans.df.columns),
            key=lambda got: len(got & want),
        )
        extra, miss = best - want, want - best
        return not extra and not miss, f"{len(want)} esperados · +{len(extra)} a mais · -{len(miss)} faltando"
    return check


def out_of_scope() -> Check:
    def check(ans: Answer) -> tuple[bool, str]:
        tipo = ans.plano.tipo if ans.plano else None
        return tipo == "fora_do_escopo", f"tipo={tipo}"
    return check


# --- casos --------------------------------------------------------------------

def _top(df: pl.DataFrame, by: str, n: int) -> dict[tuple[str, ...], int]:
    top = df.group_by(by).agg(PESSOAS.alias("n")).sort(["n", by], descending=[True, False]).head(n)
    return {(row[by],): row["n"] for row in top.iter_rows(named=True)}


@dataclass
class Case:
    id: str
    question: str
    check: Check


CASES = [
    Case("bolsas_por_regiao", "Quantas bolsas existem por região?",
         groups({(r,): v for r, v in D.group_by("regiao").agg(BOLSAS).iter_rows()})),
    Case("pessoas_pq", "Quantos pesquisadores têm bolsa PQ?",
         scalar(D.filter(pl.col("modalidade_cod") == "PQ").select(PESSOAS).item())),
    Case("dt_bahia", "Quantas bolsas DT existem na Bahia?",
         scalar(D.filter(modalidade_cod="DT", uf="BA").select(BOLSAS).item())),
    Case("top5_nordeste", "Quais as 5 instituições do Nordeste com mais bolsistas?",
         groups(_top(D.filter(regiao="Nordeste"), "instituicao", 5))),
    Case("nivel_1a", "Quantos bolsistas nível 1A existem?",
         scalar(D.filter(categoria_nivel="1A").select(PESSOAS).item())),
    Case("termino_2027_rs", "Quantas bolsas terminam em 2027 no Rio Grande do Sul?",
         scalar(D.filter(pl.col("data_termino").dt.year() == 2027, uf="RS").select(BOLSAS).item())),
    Case("lista_fisica_ufmg", "Liste os bolsistas PQ nível A de Física da UFMG",
         names(set(D.filter(modalidade_cod="PQ", categoria_nivel="A", area="Física")
                   .filter(pl.col("instituicao").str.ends_with(" UFMG"))["nome_beneficiario"]))),
    Case("computacao_sp", "Quantos bolsistas de Ciência da Computação existem no estado de São Paulo?",
         scalar(D.filter(area="Ciência da Computação", uf="SP").select(PESSOAS).item())),
    Case("bolsas_por_modalidade", "Quantas bolsas existem por modalidade?",
         groups({
             ("PQ", "Produtividade em Pesquisa"): D.filter(modalidade_cod="PQ").select(BOLSAS).item(),
             ("DT", "Produtividade Desen"): D.filter(modalidade_cod="DT").select(BOLSAS).item(),
         })),
    Case("cidade_top_sc", "Qual a cidade com mais bolsistas em Santa Catarina?",
         groups(_top(D.filter(uf="SC"), "cidade", 1))),
    Case("acento_florianopolis", "Quantos bolsistas existem em Florianópolis?",
         scalar(D.filter(cidade="Florianopolis").select(PESSOAS).item())),
    Case("inicio_2025", "Quantas bolsas começaram em 2025?",
         scalar(D.filter(pl.col("data_inicio").dt.year() == 2025).select(BOLSAS).item())),
    Case("senior_usp", "Quantos pesquisadores da USP têm bolsa sênior?",
         scalar(D.filter(categoria_nivel="SR").filter(pl.col("instituicao").str.ends_with(" USP"))
                .select(PESSOAS).item())),
    Case("nivel_escala_nova", "Quantas bolsas existem em cada nível da escala nova?",
         groups({(n,): D.filter(categoria_nivel=n).select(BOLSAS).item() for n in ("A", "B", "C")})),
    Case("fora_valor", "Qual o valor total pago em bolsas no Paraná?", out_of_scope()),
    Case("fora_genero", "Quantas mulheres têm bolsa PQ?", out_of_scope()),
]


# --- execução -----------------------------------------------------------------

async def run(runs: int, only: str | None) -> None:
    settings = get_settings()
    cases = [c for c in CASES if not only or only in c.id]
    audit = AuditLog("eval")
    db = await Database.connect()
    pipeline = await Pipeline.create(db, audit)

    results = []
    try:
        for case in cases:
            for i in range(runs):
                pipeline.reset()  # cada caso é independente
                with console.status(f"{case.id} ({i + 1}/{runs})"):
                    try:
                        ans = await pipeline.ask(case.question)
                        ok, detail = case.check(ans) if not ans.error else (False, ans.error)
                    except Exception as exc:
                        ans, ok, detail = None, False, f"{type(exc).__name__}: {exc}"
                audit.write("eval_case", case=case.id, run=i + 1, ok=ok, detail=detail)
                results.append((case, i, ok, detail, ans))
    finally:
        await db.close()

    table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
    for col in ("caso", "ok", "detalhe", "aviso", "tokens", "s"):
        table.add_column(col, justify="right" if col in ("tokens", "s") else "left")
    for case, i, ok, detail, ans in results:
        warn = ", ".join(ans.unverified_numbers) if ans and ans.unverified_numbers else ""
        table.add_row(
            case.id + (f" #{i + 1}" if runs > 1 else ""),
            "[green]✔[/green]" if ok else "[red]✘[/red]",
            detail,
            f"[yellow]{warn}[/yellow]",
            str(ans.usage.tokens_in + ans.usage.tokens_out) if ans else "",
            f"{ans.ms / 1000:.1f}" if ans else "",
        )
    console.print(table)

    passed = sum(ok for _, _, ok, _, _ in results)
    tokens = sum(a.usage.tokens_in + a.usage.tokens_out for *_, a in results if a)
    console.print(
        f"[bold]{passed}/{len(results)} corretas[/bold] ({passed / len(results):.0%}) · "
        f"{tokens:,} tokens · SQL: {settings.llm_model_sql} · resumo: {settings.summary_model}"
    )
    console.print(f"[dim]log: {audit.path.relative_to(ROOT)}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=1, help="repetições por caso")
    parser.add_argument("-k", dest="only", help="filtra casos pelo id")
    args = parser.parse_args()
    asyncio.run(run(args.runs, args.only))


if __name__ == "__main__":
    main()
