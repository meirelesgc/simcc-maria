"""Question -> several SQL steps (tool calls) -> answer.

The model may run as many queries as it needs (up to `agent_max_steps`),
including the hybrid search functions, and then writes the answer. Every step
is logged; every number in the answer is checked against the step results.
"""

import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import polars as pl
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

from simcc_maria.audit import AuditLog
from simcc_maria.catalog import ANSWER_STYLE, RULES, SCHEMA_DOC
from simcc_maria.config import get_settings
from simcc_maria.db import Database
from simcc_maria.embeddings import Embedder

HISTORY_TURNS = 3
TOOL_RESULT_ROWS = 60
TOOL_CELL_CHARS = 200


class EmbedParam(BaseModel):
    name: str = Field(description="Placeholder name used in the SQL as :name")
    text: str = Field(description="Text to embed, e.g. 'dengue e arboviroses transmitidas pelo Aedes aegypti'")


class run_sql(BaseModel):
    """Run one read-only PostgreSQL SELECT. Use :name placeholders for query embeddings."""

    purpose: str = Field(description="One short sentence, in Portuguese, saying what this query checks")
    sql: str = Field(description="A single SELECT statement")
    embed: list[EmbedParam] = Field(default_factory=list, description="Embeddings referenced as :name in the SQL")


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0

    def add(self, msg: AIMessage | None) -> None:
        meta = getattr(msg, "usage_metadata", None) or {}
        self.tokens_in += meta.get("input_tokens", 0)
        self.tokens_out += meta.get("output_tokens", 0)

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass
class Step:
    n: int
    purpose: str
    sql: str
    embed: dict[str, str]
    df: pl.DataFrame | None = None
    truncated: bool = False
    ms: int = 0
    error: str | None = None


@dataclass
class Answer:
    question: str
    steps: list[Step] = field(default_factory=list)
    text: str = ""
    unverified_numbers: list[str] = field(default_factory=list)
    hit_step_limit: bool = False
    usage: Usage = field(default_factory=Usage)
    ms: int = 0

    @property
    def last_df(self) -> pl.DataFrame | None:
        for step in reversed(self.steps):
            if step.df is not None:
                return step.df
        return None


async def build_system_prompt(db: Database) -> str:
    s = get_settings()
    q = db.fetch_values
    modalities = await q("SELECT modality || ' = ' || count(*) FROM maria.grants GROUP BY modality ORDER BY count(*) DESC")
    institutions = await q(
        "SELECT institution_acronym FROM maria.grants GROUP BY 1 ORDER BY count(*) DESC LIMIT 40"
    )
    areas = await q("SELECT DISTINCT major_area FROM maria.grants WHERE major_area IS NOT NULL ORDER BY 1")
    (facts,) = await q("""
        SELECT json_build_object(
          'grants', (SELECT count(*) FROM maria.grants),
          'grants_with_more_than_one_holder', (SELECT count(*) FROM maria.grants WHERE holder_count > 1),
          'grant_holders', (SELECT count(*) FROM maria.grant_holders),
          'holders_in_simcc', (SELECT count(*) FROM maria.grant_holders h
                               JOIN public.researcher r ON r.lattes_id = h.lattes_id),
          'grants_with_linked_researcher', (SELECT count(DISTINCT grant_id) FROM maria.grant_researchers),
          'grant_years', (SELECT min(extract(year FROM start_date)) || '-' || max(extract(year FROM end_date))
                          FROM maria.grants))::text
    """)
    return f"""\
You answer questions about research grants (bolsas) by querying PostgreSQL with the
`run_sql` tool. You may call it several times and join tables to reach the answer.

# Database
{SCHEMA_DOC.format(years_after=s.outcome_years_after)}
# Facts
{facts}
Modalities: {", ".join(modalities)}
Top institution acronyms: {", ".join(institutions)}
Major areas: {" | ".join(areas)}
Hybrid search cutoffs: theme lexical >= {s.theme_lexical_min} OR semantic >= {s.theme_semantic_min};
advisor link lexical >= {s.link_lexical_min} OR semantic >= {s.link_semantic_min}.

# Rules
{RULES}
# Answer
{ANSWER_STYLE}"""


def _bind_embeddings(sql: str, names: list[str]) -> str:
    """Replaces :name (not ::cast) by $1, $2… following the order of `names`."""
    for i, name in enumerate(names, start=1):
        sql = re.sub(rf"(?<![:\w]):{re.escape(name)}\b", f"${i}::vector", sql)
    return sql


def _result_text(step: Step) -> str:
    if step.error:
        return f"ERROR: {step.error}"
    df = step.df
    head = df.head(TOOL_RESULT_ROWS).with_columns(
        pl.col(pl.String).str.slice(0, TOOL_CELL_CHARS)
    )
    total = f"{df.height}{'+ (truncated)' if step.truncated else ''}"
    shown = f"showing first {head.height}" if df.height > head.height else "all rows shown"
    return f"rows: {total} · {shown} · {step.ms} ms\n{head.write_csv()}"


class Agent:
    def __init__(self, db: Database, embedder: Embedder, system_prompt: str, audit: AuditLog):
        s = get_settings()
        self.db = db
        self.embedder = embedder
        self.system_prompt = system_prompt
        self.audit = audit
        self.history: list[BaseMessage] = []
        # tools + reasoning_effort are only accepted by OpenAI's Responses API
        kwargs = {"api_key": s.openai_api_key.get_secret_value(), "use_responses_api": True}
        if s.llm_reasoning:
            kwargs["reasoning"] = {"effort": s.llm_reasoning}
        self.llm = init_chat_model(s.llm_model, **kwargs)
        self.llm_tools = self.llm.bind_tools([run_sql])

    @classmethod
    async def create(cls, db: Database, embedder: Embedder, audit: AuditLog) -> "Agent":
        prompt = await build_system_prompt(db)
        audit.start(prompt)
        return cls(db, embedder, prompt, audit)

    def reset(self) -> None:
        self.history.clear()

    async def _execute(self, step: Step) -> None:
        names = list(step.embed)
        args = tuple([await self.embedder.embed_one(step.embed[n]) for n in names])
        sql = _bind_embeddings(step.sql, names)
        try:
            result = await self.db.run(sql, args)
            step.df, step.truncated, step.ms = result.df, result.truncated, result.ms
        except Exception as exc:  # the error goes back to the model
            step.error = f"{type(exc).__name__}: {exc}"

    async def ask(self, question: str, on_step: Callable[[Step], Awaitable[None] | None] | None = None) -> Answer:
        s = get_settings()
        self.audit.turn += 1
        self.audit.write("question", text=question)
        start = time.perf_counter()
        ans = Answer(question=question)

        messages: list[BaseMessage] = [
            SystemMessage(self.system_prompt),
            *self.history[-HISTORY_TURNS * 2 :],
            HumanMessage(question),
        ]

        while True:
            out_of_steps = len(ans.steps) >= s.agent_max_steps
            if out_of_steps:
                ans.hit_step_limit = True
                messages.append(HumanMessage(
                    "Step limit reached. Write the final answer now with the results you have, "
                    "and say what could not be verified."
                ))
            ai = await (self.llm if out_of_steps else self.llm_tools).ainvoke(messages)
            ans.usage.add(ai)
            messages.append(ai)
            if out_of_steps or not ai.tool_calls:
                ans.text = ai.text if hasattr(ai, "text") else str(ai.content)
                break

            for call in ai.tool_calls:
                a = call["args"]
                step = Step(
                    n=len(ans.steps) + 1,
                    purpose=a.get("purpose", ""),
                    sql=a.get("sql", ""),
                    embed={e["name"]: e["text"] for e in a.get("embed") or []},
                )
                await self._execute(step)
                ans.steps.append(step)
                self.audit.write(
                    "step",
                    step=step.n,
                    purpose=step.purpose,
                    sql=step.sql,
                    embed=step.embed,
                    error=step.error,
                    rows=None if step.df is None else step.df.height,
                    truncated=step.truncated,
                    ms=step.ms,
                    sample=None if step.df is None else step.df.head(20).to_dicts(),
                )
                messages.append(ToolMessage(_result_text(step), tool_call_id=call["id"]))
                if on_step:
                    res = on_step(step)
                    if res is not None:
                        await res

        ans.unverified_numbers = unverified_numbers(
            ans.text, [st.df for st in ans.steps if st.df is not None], extra=question
        )
        self.history += [HumanMessage(question), AIMessage(ans.text)]
        ans.ms = int((time.perf_counter() - start) * 1000)
        self.audit.write(
            "answer",
            text=ans.text,
            steps=len(ans.steps),
            hit_step_limit=ans.hit_step_limit,
            unverified_numbers=ans.unverified_numbers,
            tokens_in=ans.usage.tokens_in,
            tokens_out=ans.usage.tokens_out,
            ms=ans.ms,
        )
        return ans


# --- Checking the numbers quoted in the answer --------------------------------

# Brazilian-formatted numbers (9.650 · 53,8). Ignores pieces of codes and ids
# such as "1A" or "18/2024" (they are not values quoted from a table).
_NUM = re.compile(r"(?<![\w/])(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?(?![\w/])")


def _parse_br(token: str) -> float:
    return float(token.replace(".", "").replace(",", "."))


def _numbers_in(value) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    text = str(value)
    found = [float(t) for t in re.findall(r"\d+(?:\.\d+)?", text)]  # database format
    found += [_parse_br(t) for t in _NUM.findall(text)]
    return found


def _strip_ordinals(text: str) -> str:
    """Removes numbers that only order things: '1. ' list markers and a first
    table column counting 1, 2, 3... (rank/position)."""
    lines, rank = [], 0
    for line in text.splitlines():
        line = re.sub(r"^(\s*)\d+\.\s", r"\1", line)
        cells = line.split("|")
        if len(cells) > 2 and cells[1].strip().isdigit() and int(cells[1].strip()) == rank + 1:
            rank += 1
            cells[1] = " "
            line = "|".join(cells)
        elif not line.lstrip().startswith("|"):
            rank = 0
        lines.append(line)
    return "\n".join(lines)


def unverified_numbers(text: str, dfs: list[pl.DataFrame], extra: str = "") -> list[str]:
    """Numbers in the answer that appear in no step result (nor in the question)."""
    text = _strip_ordinals(text)
    known: set[float] = set()
    for df in dfs:
        known.add(float(df.height))
        for row in df.iter_rows():
            for v in row:
                known.update(_numbers_in(v))
    known.update(_numbers_in(extra))

    # exact value, or rounded to 0, 1 or 2 decimals (53,78 → 53,8 / 54)
    def matches(x: float) -> bool:
        return x in known or any(abs(x - round(k, d)) < 1e-9 for k in known for d in (0, 1, 2))

    return list(dict.fromkeys(tok for tok in _NUM.findall(text) if not matches(_parse_br(tok))))
