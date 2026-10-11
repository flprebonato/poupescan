from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parents[3]
FRONTEND_DIR = PROJECT_DIR / "frontend"


class Settings(BaseSettings):
    app_name: str = "PoupeScan"
    database_url: str = "postgresql+psycopg://poupescan:poupescan@db:5432/poupescan"
    auth_secret_key: str = "development-only-change-this-secret-key"
    auth_token_minutes: int = 60 * 8
    cookie_secure: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3-vl:4b-instruct-q4_K_M"
    ollama_timeout: float = 900
    ollama_num_ctx: int = Field(default=4096, ge=2048)
    ollama_keep_alive: int = Field(default=60, ge=0)
    ollama_image_max_side: int = Field(default=1600, ge=640, le=3600)
    cnpj_lookup_enabled: bool = True
    cnpj_lookup_url: str = "https://minhareceita.org"
    cnpj_lookup_timeout: float = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
