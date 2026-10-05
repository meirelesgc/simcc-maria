"""Chat no terminal: poetry run maria"""

import asyncio
from datetime import date, datetime
from decimal import Decimal

import polars as pl
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from simcc_maria.audit import AuditLog
from simcc_maria.catalog import COLUMNS, TABLE
from simcc_maria.config import ROOT, get_settings
from simcc_maria.db import Database
from simcc_maria.pipeline import Answer, Pipeline

DISPLAY_ROWS = 20
BAR_WIDTH = 28

COMMANDS = {
    "/ajuda": "mostra esta ajuda",
    "/exemplos": "perguntas sugeridas",
    "/schema": "colunas da tabela",
    "/sql": "liga/desliga a exibição do SQL",
    "/csv": "exporta o último resultado completo",
    "/log": "caminho do log de auditoria da sessão",
    "/limpar": "esquece o contexto da conversa",
    "/sair": "encerra",
}

EXAMPLES = [
    "Quantas bolsas existem por região?",
    "Quais as 10 instituições do Nordeste com mais bolsistas?",
    "Liste os bolsistas PQ nível A de Física da UFMG",
    "Quantas bolsas DT existem por programa de fomento?",
    "Quantas bolsas terminam em 2027 no Rio Grande do Sul?",
    "Distribuição de níveis em Ciência da Computação",
    "Qual a cidade com mais bolsistas em Santa Catarina?",
]

console = Console()


# --- formatação ---------------------------------------------------------------

def fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "sim" if value else "não"
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    if isinstance(value, (float, Decimal)):
        return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value)


def _bar_column(df: pl.DataFrame) -> str | None:
    """Coluna numérica a desenhar como barra: a primeira, se não houver negativos."""
    for name, dtype in df.schema.items():
        if dtype.is_numeric():
            col = df[name].drop_nulls()
            if col.len() and col.min() >= 0 and col.max() > 0:
                return name
    return None


def render_table(ans: Answer) -> Table | Text:
    df = ans.df
    if df.is_empty():
        return Text("nenhuma linha encontrada", style="yellow")

    # Em listagens, colunas com o mesmo valor em todas as linhas (os filtros)
    # viram uma legenda em vez de ocupar largura repetindo o valor.
    constant: dict[str, str] = {}
    if ans.plano.tipo == "listagem" and df.height > 1 and df.width > 2:
        for name in df.columns:
            if df[name].n_unique() == 1 and len(constant) < df.width - 2:
                constant[name] = fmt(df[name][0])
        df = df.drop(list(constant))

    show = df.head(DISPLAY_ROWS)
    bar = _bar_column(df) if ans.plano.tipo == "agregacao" and 1 < df.height <= DISPLAY_ROWS else None

    table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", pad_edge=False)
    for name, dtype in show.schema.items():
        table.add_column(
            name,
            justify="right" if dtype.is_numeric() else "left",
            overflow="fold",
            min_width=min(len(name), 24),
        )
    if bar:
        table.add_column("", no_wrap=True)
        top = float(df[bar].max())

    for row in show.iter_rows(named=True):
        cells = [fmt(v) for v in row.values()]
        if bar:
            v = row[bar]
            cells.append("█" * max(1, round(float(v) / top * BAR_WIDTH)) if v else "")
        table.add_row(*cells)

    notes = []
    if constant:
        notes.append(" · ".join(f"{k} = {v}" for k, v in constant.items()))
    hidden = df.height - show.height
    if hidden > 0 or ans.truncated:
        more = f"+{fmt(hidden)}" + ("+" if ans.truncated else "")
        notes.append(f"… {more} linhas · /csv para exportar")
    if notes:
        table.caption = "\n".join(notes)
    return table


def render_answer(ans: Answer, show_sql: bool) -> None:
    settings = get_settings()
    if ans.plano is None or ans.error:
        console.print(Panel(ans.error or "sem resposta", title="erro", border_style="red"))
        return

    p = ans.plano
    if show_sql and p.sql:
        title = f"SQL · {p.tipo}"
        subtitle = f"{fmt(ans.df.height)} linhas · {ans.sql_ms} ms"
        if ans.attempts > 1:
            subtitle += f" · {ans.attempts} tentativas"
        console.print(
            Panel(
                Group(Syntax(p.sql.strip(), "sql", theme="ansi_dark", word_wrap=True), Text(p.premissas, style="dim italic")),
                title=title, subtitle=subtitle, title_align="left", subtitle_align="right",
                border_style="dim",
            )
        )

    if ans.df is not None:
        console.print(render_table(ans))

    body = [Markdown(ans.summary)]
    if ans.unverified_numbers:
        body.append(Text(
            f"⚠ números não encontrados na tabela: {', '.join(ans.unverified_numbers)}",
            style="yellow",
        ))
    models = settings.llm_model_sql.split(":")[-1]
    if settings.summary_model != settings.llm_model_sql:
        models += " / " + settings.summary_model.split(":")[-1]
    footer = f"{fmt(ans.usage.tokens_in + ans.usage.tokens_out)} tokens · {ans.ms / 1000:.1f}s · {models}"
    console.print(Panel(Group(*body), title="resumo", title_align="left", subtitle=footer,
                        subtitle_align="right", border_style="green"))


def render_help() -> None:
    t = Table(box=None, show_header=False)
    for cmd, desc in COMMANDS.items():
        t.add_row(Text(cmd, style="cyan"), desc)
    console.print(t)


def render_schema() -> None:
    t = Table(title=TABLE, box=box.SIMPLE_HEAD, header_style="bold cyan")
    t.add_column("coluna", style="cyan")
    t.add_column("tipo", style="dim")
    t.add_column("descrição")
    for name, (pg_type, desc) in COLUMNS.items():
        t.add_row(name, pg_type, desc)
    console.print(t)


# --- loop ---------------------------------------------------------------------

async def chat() -> None:
    settings = get_settings()
    audit = AuditLog("chat")
    with console.status("conectando ao banco e montando o contexto…"):
        db = await Database.connect()
        pipeline = await Pipeline.create(db, audit)

    console.print(Panel(
        Text.assemble(
            ("SIMCC Maria", "bold"), " · perguntas sobre bolsas PQ/DT do CNPq vigentes em 08/09/2026\n",
            ("modelo SQL: ", "dim"), settings.llm_model_sql, ("  ·  resumo: ", "dim"), settings.summary_model, "\n",
            ("digite ", "dim"), ("/ajuda", "cyan"), (" para comandos ou ", "dim"), ("/exemplos", "cyan"),
            (" para começar", "dim"),
        ),
        box=box.ROUNDED, border_style="cyan",
    ))

    session: PromptSession = PromptSession(
        history=FileHistory(str(ROOT / ".maria_history")),
        completer=WordCompleter(list(COMMANDS), sentence=True),
    )
    show_sql = True
    last: Answer | None = None

    try:
        while True:
            try:
                text = (await session.prompt_async("\n› ")).strip()
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            if not text:
                continue

            if text.startswith("/"):
                cmd = text.split()[0].lower()
                audit.write("command", text=text)
                if cmd == "/sair":
                    break
                elif cmd == "/ajuda":
                    render_help()
                elif cmd == "/exemplos":
                    for i, ex in enumerate(EXAMPLES, 1):
                        console.print(f"[dim]{i}.[/dim] {ex}")
                elif cmd == "/schema":
                    render_schema()
                elif cmd == "/sql":
                    show_sql = not show_sql
                    console.print(f"SQL {'visível' if show_sql else 'oculto'}", style="dim")
                elif cmd == "/csv":
                    if last is None or last.df is None:
                        console.print("nenhum resultado para exportar", style="yellow")
                    else:
                        out = settings.logs_dir / "exports" / f"{audit.session}_turno{audit.turn}.csv"
                        out.parent.mkdir(parents=True, exist_ok=True)
                        last.df.write_csv(out)
                        audit.write("export", path=out, rows=last.df.height)
                        console.print(f"exportado: {out.relative_to(ROOT)}", style="green")
                elif cmd == "/log":
                    console.print(str(audit.path.relative_to(ROOT)), style="dim")
                elif cmd == "/limpar":
                    pipeline.reset()
                    console.print("contexto da conversa apagado", style="dim")
                else:
                    console.print(f"comando desconhecido: {cmd}", style="yellow")
                continue

            try:
                with console.status("pensando…", spinner="dots"):
                    ans = await pipeline.ask(text)
            except KeyboardInterrupt:
                console.print("cancelado", style="yellow")
                continue
            except Exception as exc:  # falha de rede/API não derruba a sessão
                audit.write("exception", error=f"{type(exc).__name__}: {exc}")
                console.print(Panel(f"{type(exc).__name__}: {exc}", title="erro", border_style="red"))
                continue
            last = ans
            render_answer(ans, show_sql)
    finally:
        audit.write("session_end")
        await db.close()
        console.print(f"[dim]log da sessão: {audit.path.relative_to(ROOT)}[/dim]")


def main() -> None:
    asyncio.run(chat())


if __name__ == "__main__":
    main()
