"""Configuracion del backend, leida de variables de entorno / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = "127.0.0.1"
    db_port: int = 3307
    db_name: str = "reconciliation"
    db_user: str = "reconciler"
    db_password: str = "reconcilepass"

    # "stub" | "flaky" | "qvac" (qvac llega en la Fase 4)
    llm_client: str = "stub"
    llm_max_retries: int = 3

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
