"""Web chat: poetry run maria-web (or docker compose up -d).

One page (static/index.html) and a small JSON API. Each browser gets its own
Agent (conversation history + one JSONL audit log), identified by a cookie.
The steps are streamed as NDJSON while the agent works, like in the terminal.
"""

import asyncio
import json
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg
import polars as pl
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from simcc_maria.agent import Agent, Answer, Step, build_system_prompt
from simcc_maria.audit import AuditLog
from simcc_maria.cli import EXAMPLES, fmt
from simcc_maria.config import get_settings
from simcc_maria.db import Database
from simcc_maria.embeddings import Embedder

STEP_ROWS = 20
COOKIE = "maria_sid"
INDEX = Path(__file__).parent / "static" / "index.html"


@dataclass
class Session:
    agent: Agent
    audit: AuditLog
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last: Answer | None = None
    last_used: float = field(default_factory=time.monotonic)
    questions: int = 0
    cost_usd: float = 0.0

    def close(self) -> None:
        self.audit.write("session_end", questions=self.questions, cost_usd=round(self.cost_usd, 6))


class State:
    db: Database
    write_pool: asyncpg.Pool
    system_prompt: str
    busy: asyncio.Semaphore
    sessions: dict[str, Session]


state = State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    state.db = await Database.connect()
    # query embeddings are cached in maria.embedding_cache: this pool may write
    state.write_pool = await asyncpg.create_pool(s.asyncpg_dsn, min_size=1, max_size=2,
                                                 init=Embedder.init_connection)
    state.system_prompt = await build_system_prompt(state.db)
    state.busy = asyncio.Semaphore(s.web_max_concurrent)
    state.sessions = {}
    if s.web_password is None:
        print("WEB_PASSWORD não definido: a página está aberta para qualquer um", flush=True)
    try:
        yield
    finally:
        for sess in state.sessions.values():
            sess.close()
        await state.db.close()
        await state.write_pool.close()


def require_login(credentials: HTTPBasicCredentials | None = Depends(HTTPBasic(auto_error=False))) -> None:
    s = get_settings()
    if s.web_password is None:
        return
    ok = credentials is not None and secrets.compare_digest(
        credentials.username.encode(), s.web_user.encode()
    ) & secrets.compare_digest(credentials.password.encode(), s.web_password.get_secret_value().encode())
    if not ok:
        raise HTTPException(401, "login necessário", headers={"WWW-Authenticate": 'Basic realm="SIMCC Maria"'})


app = FastAPI(title="SIMCC Maria", lifespan=lifespan, dependencies=[Depends(require_login)],
              docs_url=None, redoc_url=None, openapi_url=None)


def _drop_idle() -> None:
    limit = get_settings().web_session_idle_min * 60
    now = time.monotonic()
    for sid, sess in list(state.sessions.items()):
        if now - sess.last_used > limit and not sess.lock.locked():
            sess.close()
            del state.sessions[sid]


@app.middleware("http")
async def session_cookie(request: Request, call_next):
    # set here, not in get_session: a returned StreamingResponse ignores dependency cookies
    sid = request.cookies.get(COOKIE)
    request.state.sid = sid or secrets.token_urlsafe(16)
    response = await call_next(request)
    if sid is None:
        response.set_cookie(COOKIE, request.state.sid, httponly=True, samesite="lax")
    return response


def get_session(request: Request) -> Session:
    _drop_idle()
    sid = request.state.sid
    sess = state.sessions.get(sid)
    if sess is None:
        audit = AuditLog("web")
        audit.start(state.system_prompt, client=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"))
        sess = Session(Agent(state.db, Embedder(state.write_pool), state.system_prompt, audit), audit)
        state.sessions[sid] = sess
    sess.last_used = time.monotonic()
    return sess


# --- serialization --------------------------------------------------------------

def step_json(step: Step) -> dict:
    out = {"type": "step", "n": step.n, "purpose": step.purpose, "sql": step.sql.strip(),
           "embed": step.embed, "ms": step.ms, "error": step.error}
    if step.df is not None:
        head = step.df.head(STEP_ROWS)
        out |= {
            "rows": step.df.height,
            "truncated": step.truncated,
            "columns": [{"name": n, "numeric": t.is_numeric()} for n, t in head.schema.items()],
            "data": [[fmt(v) for v in row] for row in head.iter_rows()],
        }
    return out


def answer_json(ans: Answer, sess: Session) -> dict:
    u = ans.usage
    return {"type": "answer", "text": ans.text, "unverified_numbers": ans.unverified_numbers,
            "hit_step_limit": ans.hit_step_limit, "steps": len(ans.steps), "ms": ans.ms,
            "tokens": u.total, "cost_usd": u.cost_usd, "session_cost_usd": sess.cost_usd,
            "questions": sess.questions}


def _line(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, default=str) + "\n").encode()


# --- routes -------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return INDEX.read_text(encoding="utf-8")


@app.get("/api/info")
async def info(sess: Session = Depends(get_session)) -> dict:
    s = get_settings()
    return {"model": s.llm_model.split(":")[-1], "max_steps": s.agent_max_steps, "examples": EXAMPLES,
            "session_cost_usd": sess.cost_usd, "questions": sess.questions}


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@app.post("/api/ask")
async def ask(q: Question, sess: Session = Depends(get_session)) -> StreamingResponse:
    if sess.lock.locked():
        raise HTTPException(409, "aguarde a resposta anterior")

    async def stream():
        async with sess.lock:
            if state.busy.locked():
                yield _line({"type": "queued"})
            async with state.busy:
                queue: asyncio.Queue[dict] = asyncio.Queue()
                get: asyncio.Task | None = None
                task = asyncio.create_task(sess.agent.ask(q.question.strip(),
                                                          on_step=lambda st: queue.put_nowait(step_json(st))))
                try:
                    while not (task.done() and queue.empty()):
                        get = asyncio.create_task(queue.get())
                        await asyncio.wait({get, task}, return_when=asyncio.FIRST_COMPLETED)
                        if get.done():
                            yield _line(get.result())
                        else:
                            get.cancel()
                    ans = task.result()
                except Exception as exc:  # network/API failures do not end the session
                    sess.audit.write("exception", error=f"{type(exc).__name__}: {exc}")
                    yield _line({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
                    return
                finally:
                    if get is not None:
                        get.cancel()
                    if not task.done():  # the browser left: stop spending tokens
                        task.cancel()
                        sess.audit.write("cancelled")
                sess.last = ans
                sess.questions += 1
                sess.cost_usd += ans.usage.cost_usd
                yield _line(answer_json(ans, sess))

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/api/reset")
async def reset(sess: Session = Depends(get_session)) -> dict:
    sess.agent.reset()
    sess.last = None
    sess.audit.write("command", text="/limpar")
    return {"ok": True}


@app.get("/api/export/{n}.csv")
async def export(n: int, sess: Session = Depends(get_session)) -> Response:
    steps = {st.n: st for st in (sess.last.steps if sess.last else []) if st.df is not None}
    if n not in steps:
        raise HTTPException(404, "passo sem resultado")
    df = steps[n].df.with_columns(pl.col(pl.List(pl.String)).list.join("; "))
    sess.audit.write("export", step=n, rows=df.height)
    return Response(df.write_csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="maria_passo{n}.csv"'})


def main() -> None:
    s = get_settings()
    uvicorn.run(app, host=s.web_host, port=s.web_port, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
