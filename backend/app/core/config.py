"""Application settings loaded from environment variables / .env (never from frontend code)."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'logmind.db').as_posix()}"
    upload_dir: str = str(BASE_DIR / "data" / "uploads")
    cache_dir: str = str(BASE_DIR / "data" / "cache")
    dataset_dir: str = str(BASE_DIR / "data" / "datasets")
    sample_dir: str = str(BASE_DIR / "sample_data")
    max_upload_mb: int = 50
    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://localhost:3000"
    rate_limit_per_minute: int = 600
    # privacy: mask sensitive values in stored messages (comma list of rules, or "none")
    mask_rules: str = "email,phone,token,password,apikey"
    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"  # any Hugging Face sentence-embedding model id
    hf_token: str = ""  # Hugging Face access token (private/gated models, higher rate limits)
    embeddings_enabled: bool = True
    # Optional LLM enhancement (the app works without a key)
    llm_provider: str = ""  # "", "openai", "gemini"
    llm_api_key: str = ""
    llm_model: str = ""
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def _driver(cls, v: str) -> str:
        """Hosts such as Render/Heroku hand out postgres:// or postgresql://; SQLAlchemy would then look for psycopg2, which is not installed."""
        v = v.strip()
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.upload_dir, s.cache_dir, s.dataset_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    return s
