from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str
    # Overrides host:port of DATABASE_URL, e.g. "db:5432" inside Docker (compose.yaml)
    database_host: str | None = None
    openai_api_key: SecretStr

    # Dated snapshot: the model does not change between audited runs
    llm_model: str = "openai:gpt-5.5-2026-04-23"
    llm_reasoning: str | None = "medium"  # OpenAI reasoning_effort
    agent_max_steps: int = 15  # tool calls per question
    embedding_model: str = "text-embedding-3-small"  # same model used by SIMCC
    # Prices in USD per 1M tokens, for the cost in the logs (openai.com/api/pricing)
    llm_price_input: float = 5.00
    llm_price_cached_input: float = 0.50
    llm_price_output: float = 30.00  # reasoning tokens are billed as output
    embedding_price: float = 0.02

    # Hybrid matching: a candidate is kept when it passes the lexical cutoff OR
    # the semantic cutoff; the weights rank the union:
    #   score = lexical_weight * lexical + semantic_weight * semantic
    # Theme search (holder records and productions): lexical = term found in the text (0/1)
    theme_lexical_min: float = 1.0
    theme_semantic_min: float = 0.40
    theme_lexical_weight: float = 0.5
    theme_semantic_weight: float = 0.5
    # Record -> advisor link (project title vs guidance title): lexical = pg_trgm similarity
    link_lexical_min: float = 0.80
    link_semantic_min: float = 0.90
    link_lexical_weight: float = 0.5
    link_semantic_weight: float = 0.5
    # Guidance year must fall within [record start - before, planned end + after]
    link_years_before: int = 1
    link_years_after: int = 2
    # Nearest guidance titles (HNSW) considered as link candidates per record
    link_candidates: int = 20
    # Productions count as outcome from the record start to its end + N years
    outcome_years_after: int = 3

    # SQL tool limits
    sql_timeout_s: int = 60  # search_productions over all 295k productions takes ~20 s
    sql_max_rows: int = 1000

    # Web interface (poetry run maria-web)
    web_host: str = "0.0.0.0"
    web_port: int = 8001
    web_user: str = "maria"
    web_password: SecretStr | None = None  # unset = no login
    web_max_concurrent: int = 3  # questions answered at the same time
    web_session_idle_min: int = 120  # idle sessions are dropped after this

    raw_scholarships: Path = ROOT / "data" / "raw" / "scholarships.parquet"
    processed_dir: Path = ROOT / "data" / "processed"
    cache_dir: Path = ROOT / "data" / "cache"
    logs_dir: Path = ROOT / "logs"

    @property
    def asyncpg_dsn(self) -> str:
        # The URL follows SQLAlchemy's format; asyncpg does not accept "+asyncpg"
        dsn = urlsplit(self.database_url.replace("postgresql+asyncpg://", "postgresql://"))
        if self.database_host:
            credentials = dsn.netloc.rpartition("@")[0]
            dsn = dsn._replace(netloc=f"{credentials}@{self.database_host}" if credentials else self.database_host)
        return urlunsplit(dsn)


@lru_cache
def get_settings() -> Settings:
    return Settings()
