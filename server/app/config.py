"""Application settings, loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # dev | staging | prod
    app_env: str = "dev"
    secret_key: str = "dev-only"

    database_url: str = "postgresql+asyncpg://agentforge:agentforge@localhost:5544/agentforge"
    sync_database_url: str = "postgresql+psycopg://agentforge:agentforge@localhost:5544/agentforge"
    redis_url: str = "redis://localhost:6390/0"

    # OpenAI-compatible LLM gateway (camel-hub) — chat planning (P-LLM) + Q-LLM
    llm_base_url: str = "https://api.camel-hub.com/v1"
    llm_api_key: str = ""
    pllm_model: str = "claude-sonnet-4-5"
    qllm_model: str = "claude-haiku-4-5"

    # Dedicated LLM for the Explorer engine (auto-adaptation: propose endpoints +
    # select operations). Separate provider/key/model from planning by design.
    # Falls back to the camel-hub gateway when unset.
    explorer_llm_base_url: str = ""
    explorer_llm_api_key: str = ""
    explorer_model: str = ""

    @property
    def explorer_base_url(self) -> str:
        return self.explorer_llm_base_url or self.llm_base_url

    @property
    def explorer_api_key(self) -> str:
        return self.explorer_llm_api_key or self.llm_api_key

    cors_origins: str = "http://localhost:5173,http://localhost:4173"

    # ── observability ──
    log_dir: str = ""          # empty = stdout only; set e.g. /var/log/agent-forge in prod
    log_level: str = "INFO"
    log_json: bool = False     # structured JSON logs (recommended in prod)

    # ── auth ──
    # demo role-login (pick a role, no password). Auto-disabled outside dev.
    demo_login: bool | None = None
    session_ttl_days: int = 7

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env not in ("dev", "test", "local")

    @property
    def demo_login_enabled(self) -> bool:
        return (not self.is_prod) if self.demo_login is None else self.demo_login

    def validate_production(self) -> list[str]:
        """Return a list of fatal misconfigurations for a production boot."""
        problems: list[str] = []
        if not self.is_prod:
            return problems
        if self.secret_key in ("", "dev-only") or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a strong (>=32 char) random value in prod")
        if not self.llm_api_key:
            problems.append("LLM_API_KEY must be set")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must list exact origins (no '*') with credentials")
        if "localhost" in self.database_url or "agentforge:agentforge@" in self.database_url:
            problems.append("DATABASE_URL must use a real host and a non-default DB password")
        if self.demo_login_enabled:
            problems.append("DEMO_LOGIN must be false in prod (use password/OIDC auth)")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
