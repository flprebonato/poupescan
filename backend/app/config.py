from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PoupeScan"
    database_url: str = "postgresql+psycopg://poupescan:poupescan@db:5432/poupescan"
    auth_secret_key: str = "development-only-change-this-secret-key"
    auth_token_minutes: int = 60 * 8
    cookie_secure: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
