"""Terminal chat: poetry run maria"""

import asyncio
from datetime import date, datetime
from decimal import Decimal

import asyncpg
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

from simcc_maria.agent import Agent, Answer, Step
from simcc_maria.audit import AuditLog
from simcc_maria.catalog import SCHEMA_DOC
from simcc_maria.config import ROOT, get_settings
from simcc_maria.db import Database
from simcc_maria.embeddings import Embedder

STEP_ROWS = 8
BAR_WIDTH = 24

COMMANDS = {
    "/ajuda": "mostra esta ajuda",
    "/exemplos": "perguntas sugeridas",
    "/schema": "tabelas e funções disponíveis",
    "/sql": "liga/desliga o SQL de cada passo",
    "/csv": "exporta os resultados de todos os passos da última resposta",
    "/log": "caminho do log de auditoria da sessão",
    "/limpar": "esquece o contexto da conversa",
    "/sair": "encerra",
}

EXAMPLES = [
    "As bolsas contemplam pesquisas na temática Dengue? Se sim, qual o resultado desse fomento? "
    "Ele gerou artigos? livros? capítulos? de quem, quando e quantos",
    "Quantos bolsistas existem por modalidade?",
    "Quantas bolsas existem?",
    "Quantas pessoas fizeram IC e depois mestrado?",
    "Quais as 10 instituições com mais bolsistas de doutorado?",
    "Existem bolsistas pesquisando inteligência artificial? Quantos por ano?",
    "Quais orientadores aparecem ligados a mais bolsistas que pesquisam Zika?",
]

console = Console()


# --- formatting ---------------------------------------------------------------

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
    if isinstance(value, list):
        return "; ".join(map(str, value))
    return str(value)


def _bar_column(df: pl.DataFrame) -> str | None:
    """Numeric column drawn as bars: the last one, if non-negative and not an id/year."""
    numeric = [n for n, t in df.schema.items() if t.is_numeric() and "year" not in n and "ano" not in n]
    for name in reversed(numeric):
        col = df[name].drop_nulls()
        if col.len() and col.min() >= 0 and col.max() > 0:
            return name
    return None


def render_df(df: pl.DataFrame, truncated: bool, max_rows: int) -> Table | Text:
    if df.is_empty():
        return Text("nenhuma linha", style="yellow")
    show = df.head(max_rows)
    text_cols = [n for n, t in df.schema.items() if not t.is_numeric()]
    bar = _bar_column(df) if 1 < df.height <= 20 and len(text_cols) >= 1 else None

    table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", pad_edge=False)
    for name, dtype in show.schema.items():
        table.add_column(name, justify="right" if dtype.is_numeric() else "left",
                         overflow="fold", min_width=min(len(name), 16), max_width=60)
    if bar:
        table.add_column("", no_wrap=True)
        top = float(df[bar].max())
    for row in show.iter_rows(named=True):
        cells = [fmt(v) for v in row.values()]
        if bar:
            v = row[bar]
            cells.append("█" * max(1, round(float(v) / top * BAR_WIDTH)) if v else "")
        table.add_row(*cells)

    hidden = df.height - show.height
    if hidden > 0 or truncated:
        table.caption = f"… +{fmt(hidden)}{'+' if truncated else ''} linhas · /csv para exportar"
    return table


def render_step(step: Step, show_sql: bool) -> None:
    parts = []
    if show_sql:
        parts.append(Syntax(step.sql.strip(), "sql", theme="ansi_dark", word_wrap=True))
        for name, text in step.embed.items():
            parts.append(Text(f":{name} = embedding(\"{text}\")", style="magenta"))
    if step.error:
        parts.append(Text(step.error, style="red"))
        subtitle = "erro"
    else:
        parts.append(render_df(step.df, step.truncated, STEP_ROWS))
        subtitle = f"{fmt(step.df.height)} linhas · {step.ms} ms"
    console.print(Panel(
        Group(*parts), title=f"passo {step.n} · {step.purpose}", title_align="left",
        subtitle=subtitle, subtitle_align="right", border_style="red" if step.error else "dim",
    ))


def render_answer(ans: Answer) -> None:
    s = get_settings()
    body = [Markdown(ans.text or "_sem resposta_")]
    if ans.unverified_numbers:
        body.append(Text(f"⚠ números não encontrados nos resultados: {', '.join(ans.unverified_numbers)}",
                         style="yellow"))
    if ans.hit_step_limit:
        body.append(Text(f"⚠ limite de {s.agent_max_steps} passos atingido", style="yellow"))
    footer = (f"{len(ans.steps)} passos · {fmt(ans.usage.total)} tokens · US$ {ans.usage.cost_usd:.3f} · "
              f"{ans.ms / 1000:.1f}s · "
              f"{s.llm_model.split(':')[-1]}")
    console.print(Panel(Group(*body), title="resposta", title_align="left", subtitle=footer,
                        subtitle_align="right", border_style="green"))


def render_help() -> None:
    t = Table(box=None, show_header=False)
    for cmd, desc in COMMANDS.items():
        t.add_row(Text(cmd, style="cyan"), desc)
    console.print(t)


# --- loop ---------------------------------------------------------------------

async def chat() -> None:
    s = get_settings()
    audit = AuditLog("chat")
    with console.status("conectando ao banco e montando o contexto…"):
        db = await Database.connect()
        # query embeddings are cached in maria.embedding_cache: this pool may write
        write_pool = await asyncpg.create_pool(s.asyncpg_dsn, min_size=1, max_size=2,
                                               init=Embedder.init_connection)
        agent = await Agent.create(db, Embedder(write_pool), audit)

    console.print(Panel(
        Text.assemble(
            ("SIMCC Maria", "bold"), " · bolsistas (IC, mestrado, doutorado) e a produção associada no SIMCC\n",
            ("modelo: ", "dim"), s.llm_model, ("  ·  até ", "dim"), str(s.agent_max_steps), (" consultas por pergunta\n", "dim"),
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
                    console.print(Markdown(SCHEMA_DOC.format(years_after=s.outcome_years_after)))
                elif cmd == "/sql":
                    show_sql = not show_sql
                    console.print(f"SQL {'visível' if show_sql else 'oculto'}", style="dim")
                elif cmd == "/csv":
                    steps = [st for st in (last.steps if last else []) if st.df is not None]
                    if not steps:
                        console.print("nenhum resultado para exportar", style="yellow")
                    for st in steps:
                        out = s.logs_dir / "exports" / f"{audit.session}_turn{audit.turn}_step{st.n}.csv"
                        out.parent.mkdir(parents=True, exist_ok=True)
                        st.df.with_columns(pl.col(pl.List(pl.String)).list.join("; ")).write_csv(out)
                        audit.write("export", path=out, rows=st.df.height)
                        console.print(f"exportado: {out.relative_to(ROOT)}", style="green")
                elif cmd == "/log":
                    console.print(str(audit.path.relative_to(ROOT)), style="dim")
                elif cmd == "/limpar":
                    agent.reset()
                    console.print("contexto da conversa apagado", style="dim")
                else:
                    console.print(f"comando desconhecido: {cmd}", style="yellow")
                continue

            status = console.status("pensando…", spinner="dots")
            status.start()

            def on_step(step: Step) -> None:
                status.stop()
                render_step(step, show_sql)
                status.update("pensando…")
                status.start()

            try:
                ans = await agent.ask(text, on_step=on_step)
            except KeyboardInterrupt:
                console.print("cancelado", style="yellow")
                continue
            except Exception as exc:  # network/API failures do not end the session
                audit.write("exception", error=f"{type(exc).__name__}: {exc}")
                console.print(Panel(f"{type(exc).__name__}: {exc}", title="erro", border_style="red"))
                continue
            finally:
                status.stop()
            last = ans
            render_answer(ans)
    finally:
        audit.write("session_end")
        await db.close()
        await write_pool.close()
        console.print(f"[dim]log da sessão: {audit.path.relative_to(ROOT)}[/dim]")


def main() -> None:
    asyncio.run(chat())


if __name__ == "__main__":
    main()
