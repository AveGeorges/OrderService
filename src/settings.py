from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _to_asyncpg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


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

    # LMS / local Postgres (имена как в Portal)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_username: str = "postgres"
    postgres_password: str = "postgres"
    postgres_database_name: str = "orders"
    postgres_connection_string: str | None = None

    # Опциональный полный URL (если задан — имеет приоритет)
    database_url_override: str | None = Field(
        default=None,
        validation_alias="DATABASE_URL",
    )

    database_auto_create: bool = True

    capashino_base_url: str = "https://capashino.dev-2.python-labs.ru"
    api_token: str = ""

    order_service_internal_url: str = (
        "http://student-avegeorges-order-service-web"
        ".student-avegeorges-order-service.svc:8000"
    )

    kafka_bootstrap_servers: str = ""
    kafka_order_events_topic: str = "student_system-order.events"
    kafka_shipment_events_topic: str = "student_system-shipment.events"
    kafka_consumer_group_id: str = "order-service-shipment"

    outbox_poll_interval_seconds: float = 2.0
    outbox_batch_size: int = 100
    outbox_max_retries: int = 5

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return _to_asyncpg_url(self.database_url_override)
        if self.postgres_connection_string:
            return _to_asyncpg_url(self.postgres_connection_string)

        user = quote_plus(self.postgres_username)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_database_name}"
        )

    @property
    def payment_callback_url(self) -> str:
        base = self.order_service_internal_url.rstrip("/")
        return f"{base}/api/orders/payment-callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
