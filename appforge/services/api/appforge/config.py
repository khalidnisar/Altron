"""Central configuration for the AppForge AI platform.

Every external dependency is optional. When credentials are absent the platform
runs in ``offline`` mode: deterministic stub providers replace live Play Store
scraping, LLM calls, image generation, device farms, and Play Console uploads so
the whole pipeline stays runnable (and testable) without paid API keys.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APPFORGE_", env_file=".env", extra="ignore")

    # --- core -------------------------------------------------------------
    environment: str = "development"
    database_url: str = "postgresql+psycopg://appforge:appforge@db:5432/appforge"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # Operator token protects mutating endpoints. Empty = open (dev only).
    operator_token: str = ""

    # --- agent runtime ----------------------------------------------------
    worker_poll_seconds: float = 2.0
    worker_batch_size: int = 4
    task_max_attempts: int = 3

    # --- providers (blank => deterministic offline stub) -------------------
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_model: str = "gpt-4o"
    image_model: str = "dall-e-3"

    sensortower_api_key: str = ""
    dataai_api_key: str = ""
    browserstack_user: str = ""
    browserstack_key: str = ""
    genymotion_api_key: str = ""
    play_console_service_account_json: str = ""
    admob_app_id: str = ""
    revenuecat_api_key: str = ""
    sentry_dsn: str = ""

    storage_backend: str = "local"  # local | s3 | r2
    storage_root: str = "/data/artifacts"
    storage_public_base: str = "http://localhost:8000/artifacts"

    # --- pipeline policy (blueprint sections 2.4, 6.7, 7.6) ----------------
    clone_score_threshold: int = 70
    discovery_top_n_per_niche: int = 100
    review_scrape_target: int = 10_000
    require_human_approval: bool = True

    @property
    def offline_mode(self) -> bool:
        return not (self.openai_api_key or self.anthropic_api_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
