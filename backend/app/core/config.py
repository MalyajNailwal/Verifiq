"""Application configuration loaded from environment / .env file."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central, typed application settings.

    Values come from environment variables (prefixed-free) or a `.env` file at
    the repository root. All defaults are safe for local development.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+psycopg://rwa:rwa_dev_password@localhost:5432/rwa_diligence",
        alias="DATABASE_URL",
    )
    db_echo: bool = Field(default=False, alias="DB_ECHO")

    # --- LLM provider: claude | openai | gemini | mock ---
    llm_provider: str = Field(default="claude", alias="LLM_PROVIDER")
    llm_model: str = Field(default="claude-sonnet-4-20250514", alias="LLM_MODEL")
    llm_max_retries: int = Field(default=2, alias="LLM_MAX_RETRIES")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )

    # --- Pipeline ---
    # Fields/flags below this confidence go to human review (hard constraint #3).
    confidence_threshold: float = Field(default=0.75, alias="CONFIDENCE_THRESHOLD")
    valuation_max_age_months: int = Field(default=12, alias="VALUATION_MAX_AGE_MONTHS")
    area_mismatch_tolerance_pct: float = Field(default=2.0, alias="AREA_MISMATCH_TOLERANCE_PCT")

    # --- Storage ---
    storage_dir: str = Field(default="./storage", alias="STORAGE_DIR")

    # --- App ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    app_name: str = "RWA DiligenceAI"
    disclaimer: str = (
        "This report is an automated document-verification and risk-flagging output. "
        "It is NOT investment advice and must not be relied upon to buy, sell, or "
        "invest in any asset. A qualified human reviewer must validate all flagged "
        "items before any further use."
    )

    @field_validator("llm_provider")
    @classmethod
    def _check_provider(cls, v: str) -> str:
        allowed = {"claude", "openai", "gemini", "openrouter", "mock"}
        v = v.lower().strip()
        if v not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {sorted(allowed)}, got '{v}'")
        return v

    @field_validator("confidence_threshold")
    @classmethod
    def _check_threshold(cls, v: float) -> float:
        if not 0.0 < v <= 1.0:
            raise ValueError("CONFIDENCE_THRESHOLD must be in (0, 1]")
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (use dependency override in tests)."""
    return Settings()  # type: ignore[call-arg]  # populated from env
