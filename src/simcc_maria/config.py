from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str
    openai_api_key: SecretStr

    # Dated snapshot: the model does not change between audited runs
    llm_model: str = "openai:gpt-5.5-2026-04-23"
    llm_reasoning: str | None = "medium"  # OpenAI reasoning_effort
    agent_max_steps: int = 15  # tool calls per question
    embedding_model: str = "text-embedding-3-small"  # same model used by SIMCC

    # Hybrid matching: a candidate is kept when it passes the lexical cutoff OR
    # the semantic cutoff; the weights rank the union:
    #   score = lexical_weight * lexical + semantic_weight * semantic
    # Theme search (grants and productions): lexical = term found in the text (0/1)
    theme_lexical_min: float = 1.0
    theme_semantic_min: float = 0.40
    theme_lexical_weight: float = 0.5
    theme_semantic_weight: float = 0.5
    # Grant -> advisor link (grant title vs guidance title): lexical = pg_trgm similarity
    link_lexical_min: float = 0.80
    link_semantic_min: float = 0.90
    link_lexical_weight: float = 0.5
    link_semantic_weight: float = 0.5
    # Guidance year must fall within [grant start - before, planned end + after]
    link_years_before: int = 1
    link_years_after: int = 2
    # Nearest guidance titles (HNSW) considered as link candidates per grant
    link_candidates: int = 20
    # Productions count as grant outcome from grant start to end + N years
    outcome_years_after: int = 3

    # SQL tool limits
    sql_timeout_s: int = 60  # search_productions over all 295k productions takes ~20 s
    sql_max_rows: int = 1000

    raw_scholarships: Path = ROOT / "data" / "raw" / "scholarships.parquet"
    processed_dir: Path = ROOT / "data" / "processed"
    cache_dir: Path = ROOT / "data" / "cache"
    logs_dir: Path = ROOT / "logs"

    @property
    def asyncpg_dsn(self) -> str:
        # The URL follows SQLAlchemy's format; asyncpg does not accept "+asyncpg"
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
