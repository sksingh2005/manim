"""Central config via environment variables."""

from enum import Enum
from pathlib import Path
from tempfile import gettempdir

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    openai = "openai"
    anthropic = "anthropic"
    google = "google"


class RenderQuality(str, Enum):
    l = "l"  # 480p, fast preview
    m = "m"  # 720p
    h = "h"  # 1080p
    k = "k"  # 4k, slow — disabled by default


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LangChain / LLM
    llm_provider: LLMProvider = LLMProvider.openai
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None  # GOOGLE_API_KEY / GEMINI_API_KEY
    llm_temperature: float = 0.2
    llm_timeout: int = 120
    llm_rate_limit_retries: int = Field(default=2, ge=0, le=5)
    llm_rate_limit_wait_sec: int = Field(default=65, ge=1, le=3600)
    planning_repair_attempts: int = Field(default=1, ge=0, le=2)

    # Render
    jobs_dir: str = str(Path(gettempdir()) / "manim-jobs")
    database_path: str = str(Path(gettempdir()) / "manim-state" / "jobs.sqlite3")
    render_timeout_sec: int = 300
    max_prompt_chars: int = 2000
    allow_high_quality: bool = False

    # Auth (optional MVP gate)
    api_key: str | None = None  # if set, require x-api-key header

    r2_endpoint_url: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str | None = None
    video_url_ttl_sec: int = 3600

    qdrant_url: str | None = None
    qdrant_collection: str = "manim_videos"
    embedding_model: str = "models/gemini-embedding-001"
    similarity_threshold: float = 0.93


settings = Settings()
