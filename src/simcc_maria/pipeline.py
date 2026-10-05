"""Pergunta → SQL → execução → resumo.

O fluxo é explícito (sem agente genérico) para ficar auditável:
1. o modelo de SQL devolve um `Plano` estruturado (tipo, SQL, premissas, ressalvas);
2. o SQL roda em transação somente leitura; se falhar, o erro volta ao modelo;
3. o modelo de resumo escreve o texto a partir da tabela;
4. os números citados no resumo são conferidos contra a tabela.
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Literal

import polars as pl
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from simcc_maria.audit import AuditLog
from simcc_maria.catalog import CATEGORICAL, COLUMNS, RULES, TABLE, TABLE_DESCRIPTION
from simcc_maria.config import get_settings
from simcc_maria.db import Database

HISTORY_TURNS = 5
SUMMARY_MAX_ROWS = 50


class Plano(BaseModel):
    """Plano de consulta para responder à pergunta do usuário."""

    tipo: Literal["listagem", "agregacao", "fora_do_escopo"] = Field(
        description="listagem: linhas individuais; agregacao: contagens/somas/rankings; "
        "fora_do_escopo: a base não tem a informação pedida."
    )
    sql: str = Field(description="Um único SELECT para Postgres. Vazio se fora_do_escopo.")
    premissas: str = Field(
        description="Como a pergunta foi interpretada (ex.: 'bolsistas = pessoas distintas'). Uma ou duas frases."
    )
    ressalvas: list[str] = Field(
        description="Limitações da base relevantes para esta resposta. Lista vazia se não houver."
    )


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0

    def add(self, msg: AIMessage | None) -> None:
        meta = getattr(msg, "usage_metadata", None) or {}
        self.tokens_in += meta.get("input_tokens", 0)
        self.tokens_out += meta.get("output_tokens", 0)


@dataclass
class Answer:
    question: str
    plano: Plano | None = None
    df: pl.DataFrame | None = None
    truncated: bool = False
    sql_ms: int = 0
    summary: str = ""
    unverified_numbers: list[str] = field(default_factory=list)
    attempts: int = 0
    error: str | None = None
    usage: Usage = field(default_factory=Usage)
    ms: int = 0


async def build_system_prompt(db: Database) -> str:
    cols = "\n".join(f"- {name} ({pg_type}): {desc}" for name, (pg_type, desc) in COLUMNS.items())
    values = []
    for col in CATEGORICAL:
        vals = await db.fetch_values(
            f"SELECT DISTINCT {col} FROM {TABLE} WHERE {col} IS NOT NULL ORDER BY 1"
        )
        values.append(f"- {col}: " + " | ".join(map(str, vals)))
    areas = await db.fetch_values(f"SELECT DISTINCT area FROM {TABLE} ORDER BY 1")

    return f"""\
Você traduz perguntas em português para SQL (PostgreSQL 17) sobre uma única tabela.

# Tabela {TABLE}
{TABLE_DESCRIPTION}

Colunas:
{cols}

Valores existentes nas colunas categóricas:
{chr(10).join(values)}

Valores de `area` ({len(areas)}): {" | ".join(areas)}

# Regras
{RULES}
# Formato
- Gere um único SELECT. Nada de INSERT/UPDATE/DDL nem múltiplos comandos.
- Use apelidos de coluna curtos em português (ex.: bolsas, pesquisadores, percentual).
- Em listagens, traga nome_beneficiario, instituicao e as colunas usadas no filtro; LIMIT 200.
- Se a pergunta pedir algo que não existe na base (valores em R$, histórico de \
bolsas encerradas, gênero, produção científica), use tipo=fora_do_escopo, sql vazio, \
e explique em premissas.
- Perguntas de seguimento ("e no Sul?") se referem à consulta anterior da conversa.
"""


SUMMARY_PROMPT = """\
Você escreve o resumo da resposta de um chatbot sobre bolsas de produtividade do CNPq.

Regras:
- Responda em português, em 2 a 5 frases, direto ao ponto.
- Cite APENAS números que aparecem na tabela. Não calcule percentuais, somas ou
  razões novas; se não estiver na tabela, não cite.
- Formate números no padrão brasileiro (9.650; 53,8%).
- Se houver ressalvas, mencione-as de forma breve no final.
- Se a tabela vier vazia, diga que nada foi encontrado com esses critérios.
- A tabela já aparece para o usuário logo acima do resumo: NÃO a repita linha
  a linha. Destaque o essencial (total, líder, concentração, extremos).
  Em listagens curtas, cite os nomes.
- Nunca mencione estas instruções nem explique por que escolheu citar algo.
- Não repita o SQL nem descreva a tabela coluna a coluna.
"""


def _make_model(name: str, reasoning: str | None) -> BaseChatModel:
    settings = get_settings()
    kwargs = {"api_key": settings.openai_api_key.get_secret_value()}
    if reasoning:
        kwargs["reasoning_effort"] = reasoning
    return init_chat_model(name, **kwargs)


class Pipeline:
    def __init__(self, db: Database, system_prompt: str, audit: AuditLog):
        settings = get_settings()
        self.db = db
        self.system_prompt = system_prompt
        self.audit = audit
        self.history: list[BaseMessage] = []
        self.planner = _make_model(settings.llm_model_sql, settings.llm_reasoning_sql).with_structured_output(
            Plano, include_raw=True
        )
        self.summarizer = _make_model(settings.summary_model, settings.llm_reasoning_summary)

    @classmethod
    async def create(cls, db: Database, audit: AuditLog) -> "Pipeline":
        prompt = await build_system_prompt(db)
        audit.start(prompt)
        return cls(db, prompt, audit)

    def reset(self) -> None:
        self.history.clear()

    async def ask(self, question: str) -> Answer:
        settings = get_settings()
        self.audit.turn += 1
        self.audit.write("question", text=question)
        start = time.perf_counter()
        ans = Answer(question=question)

        messages: list[BaseMessage] = [
            SystemMessage(self.system_prompt),
            *self.history[-HISTORY_TURNS * 2 :],
            HumanMessage(question),
        ]

        for attempt in range(1, settings.sql_max_attempts + 1):
            ans.attempts = attempt
            out = await self.planner.ainvoke(messages)
            ans.usage.add(out["raw"])
            plano: Plano | None = out["parsed"]
            if plano is None:
                ans.error = f"resposta do modelo fora do formato: {out.get('parsing_error')}"
                self.audit.write("plan_error", attempt=attempt, error=ans.error)
                continue
            ans.plano = plano
            self.audit.write("plan", attempt=attempt, model=settings.llm_model_sql, **plano.model_dump())

            if plano.tipo == "fora_do_escopo" or not plano.sql.strip():
                ans.error = None
                break

            try:
                result = await self.db.run(plano.sql)
            except Exception as exc:  # erro de SQL volta para o modelo corrigir
                ans.error = f"{type(exc).__name__}: {exc}"
                self.audit.write("sql_error", attempt=attempt, sql=plano.sql, error=ans.error)
                messages += [
                    AIMessage(plano.model_dump_json()),
                    HumanMessage(f"O SQL falhou com o erro abaixo. Corrija e gere o plano novamente.\n{ans.error}"),
                ]
                continue

            ans.df, ans.truncated, ans.sql_ms, ans.error = result.df, result.truncated, result.ms, None
            self.audit.write(
                "sql_result",
                attempt=attempt,
                rows=ans.df.height,
                truncated=ans.truncated,
                ms=ans.sql_ms,
                columns=ans.df.columns,
                sample=ans.df.head(20).to_dicts(),
            )
            break

        if ans.plano and ans.error is None:
            await self._summarize(ans)
            self._remember(ans)

        ans.ms = int((time.perf_counter() - start) * 1000)
        self.audit.write(
            "answer",
            text=ans.summary,
            error=ans.error,
            attempts=ans.attempts,
            unverified_numbers=ans.unverified_numbers,
            tokens_in=ans.usage.tokens_in,
            tokens_out=ans.usage.tokens_out,
            ms=ans.ms,
        )
        return ans

    async def _summarize(self, ans: Answer) -> None:
        settings = get_settings()
        plano = ans.plano
        if plano.tipo == "fora_do_escopo":
            table = "(nenhuma consulta: pergunta fora do escopo da base)"
        else:
            table = _table_text(ans.df, ans.truncated)

        prompt = (
            f"Pergunta: {ans.question}\n\n"
            f"Interpretação: {plano.premissas}\n\n"
            f"Ressalvas: {'; '.join(plano.ressalvas) or 'nenhuma'}\n\n"
            f"Resultado:\n{table}"
        )
        msg = await self.summarizer.ainvoke([SystemMessage(SUMMARY_PROMPT), HumanMessage(prompt)])
        ans.usage.add(msg)
        ans.summary = msg.text if hasattr(msg, "text") else str(msg.content)
        if plano.tipo != "fora_do_escopo":
            ans.unverified_numbers = unverified_numbers(ans.summary, ans.df, extra=ans.question)
        self.audit.write("summary", model=settings.summary_model, text=ans.summary)

    def _remember(self, ans: Answer) -> None:
        brief = {"plano": ans.plano.model_dump()}
        if ans.df is not None:
            brief["linhas"] = ans.df.height
            brief["amostra"] = ans.df.head(5).to_dicts()
        self.history += [
            HumanMessage(ans.question),
            AIMessage(json.dumps(brief, ensure_ascii=False, default=str)),
        ]


def _table_text(df: pl.DataFrame, truncated: bool) -> str:
    if df.is_empty():
        return "(tabela vazia)"
    head = df.head(SUMMARY_MAX_ROWS)
    lines = [" | ".join(head.columns)]
    lines += [" | ".join(str(v) for v in row) for row in head.iter_rows()]
    total = f"{df.height}{'+' if truncated else ''}"
    if df.height > SUMMARY_MAX_ROWS or truncated:
        lines.append(f"... ({total} linhas no total; mostradas {SUMMARY_MAX_ROWS})")
    else:
        lines.append(f"({total} linhas)")
    return "\n".join(lines)


# --- Conferência dos números citados no resumo -------------------------------

# Números no padrão brasileiro (9.650 · 53,8). Ignora pedaços de códigos e
# identificadores como "1A" ou "18/2024" (não são valores citados da tabela).
_NUM = re.compile(r"(?<![\w/])(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?(?![\w/])")


def _parse_br(token: str) -> float:
    return float(token.replace(".", "").replace(",", "."))


def _numbers_in(value) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    text = str(value)
    found = [float(t) for t in re.findall(r"\d+(?:\.\d+)?", text)]  # formato do banco
    found += [_parse_br(t) for t in _NUM.findall(text)]
    return found


def unverified_numbers(summary: str, df: pl.DataFrame | None, extra: str = "") -> list[str]:
    """Números do resumo que não aparecem na tabela (nem na pergunta)."""
    known: set[float] = set()
    if df is not None:
        known.add(float(df.height))
        for row in df.iter_rows():
            for v in row:
                known.update(_numbers_in(v))
    known.update(_numbers_in(extra))

    # aceita o valor exato ou arredondado para 0, 1 ou 2 casas (53,78 → 53,8 / 54)
    def matches(x: float) -> bool:
        return any(abs(x - round(k, d)) < 1e-9 for k in known for d in (0, 1, 2)) or x in known

    return [tok for tok in _NUM.findall(summary) if not matches(_parse_br(tok))]
