"""Application settings, loaded from environment variables and `.env`."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "FitTrack"
    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api"
    cors_origins: list[str] = ["http://localhost:5180"]
    host: str = "0.0.0.0"
    port: int = 8010

    # LLM (Groq)
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    llm_temperature: float = 0.4
    llm_max_tokens: int = 8192
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3  # transient errors (429/5xx/connection), with visible status
    llm_reasoning_effort: Literal["low", "medium", "high"] | None = "medium"

    # LangSmith tracing (optional; works out of the box with LangChain models and tools)
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "fittrack"

    # Agent
    agent_max_steps: int = 8
    agent_max_ui_repairs: int = 2
    history_max_messages: int = 40
    tool_result_max_chars: int = 12_000
    history_tool_result_chars: int = 1_500  # past turns' tool results are truncated to this

    # Database
    database_url: str = "sqlite+aiosqlite:///./fittrack.db"
    database_echo: bool = False

    # Users (single demo user until auth lands)
    default_user_id: str = "demo"
    seed_demo_data: bool = True

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    @property
    def llm_configured(self) -> bool:
        return bool(self.groq_api_key and self.groq_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
