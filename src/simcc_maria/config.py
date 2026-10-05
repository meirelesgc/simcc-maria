from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str
    openai_api_key: SecretStr

    # Modelo que gera o SQL (etapa crítica) e modelo que escreve o resumo.
    # Se LLM_MODEL_SUMMARY não for definido, usa o mesmo de LLM_MODEL_SQL.
    # Snapshots datados: o modelo não muda por baixo entre execuções auditadas.
    llm_model_sql: str = "openai:gpt-5.5-2026-04-23"
    llm_model_summary: str | None = None
    # reasoning_effort dos modelos OpenAI (none, low, medium, high)
    llm_reasoning_sql: str | None = "medium"
    llm_reasoning_summary: str | None = "low"
    embedding_model: str = "text-embedding-3-small"

    # Limites da tool de SQL
    sql_timeout_s: int = 15
    sql_max_rows: int = 1000
    sql_max_attempts: int = 3

    raw_xlsx: Path = ROOT / "data" / "raw" / "raw-data.xlsx"
    processed_csv: Path = ROOT / "data" / "processed" / "bolsas_pq_dt.csv"
    logs_dir: Path = ROOT / "logs"

    @property
    def asyncpg_dsn(self) -> str:
        # A URL segue o formato do SQLAlchemy; o asyncpg não aceita o "+asyncpg"
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")

    @property
    def summary_model(self) -> str:
        return self.llm_model_summary or self.llm_model_sql


@lru_cache
def get_settings() -> Settings:
    return Settings()
