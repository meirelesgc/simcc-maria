"""Log de auditoria: um arquivo JSONL por sessão em logs/.

Cada linha é um evento com ts, session, turn e event. Para analisar:
    SELECT * FROM read_json('logs/*.jsonl')        -- DuckDB
    pl.read_ndjson('logs/*.jsonl')                 -- polars
"""

import hashlib
import json
import secrets
import subprocess
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from simcc_maria.config import ROOT, get_settings


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=2,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


class AuditLog:
    def __init__(self, kind: str = "chat"):
        self.session = secrets.token_hex(3)
        self.turn = 0
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        logs_dir = get_settings().logs_dir
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.path = logs_dir / f"{stamp}_{kind}_{self.session}.jsonl"

    def write(self, event: str, **data) -> None:
        record = {
            "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "session": self.session,
            "turn": self.turn,
            "event": event,
            **data,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=_default) + "\n")

    def start(self, system_prompt: str, **extra) -> None:
        settings = get_settings()
        self.write(
            "session_start",
            sql_model=settings.llm_model_sql,
            summary_model=settings.summary_model,
            sql_reasoning=settings.llm_reasoning_sql,
            summary_reasoning=settings.llm_reasoning_summary,
            prompt_sha=sha256_text(system_prompt),
            csv_sha=sha256_file(settings.processed_csv),
            git_commit=git_commit(),
            system_prompt=system_prompt,
            **extra,
        )
