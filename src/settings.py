from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "order-service"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/orders"

    capashino_base_url: str = "https://capashino.dev-2.python-labs.ru"
    api_token: str = ""

    order_service_internal_url: str = (
        "http://order-service.default.svc:8000"
    )

    kafka_bootstrap_servers: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
