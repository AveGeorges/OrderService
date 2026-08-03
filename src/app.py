import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from infrastructure.messaging.workers import (
    outbox_worker_loop,
    shipment_consumer_loop,
)
from infrastructure.persistence.database import create_engine, create_session_factory
from infrastructure.persistence.models import Base
from presentation.api.exception_handlers import register_exception_handlers
from presentation.api.routes import health, orders
from settings import Settings, get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    app.state.engine = engine
    app.state.session_factory = session_factory

    if settings.database_auto_create:
        logger.info("Creating database tables if missing")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    stop = asyncio.Event()
    worker_tasks: list[asyncio.Task[None]] = []

    if settings.kafka_bootstrap_servers and settings.run_kafka_workers_in_api:
        logger.info("Starting Kafka workers inside API process")
        worker_tasks = [
            asyncio.create_task(
                outbox_worker_loop(session_factory, settings, stop),
                name="outbox-worker",
            ),
            asyncio.create_task(
                shipment_consumer_loop(session_factory, settings, stop),
                name="shipment-consumer",
            ),
        ]
    elif not settings.kafka_bootstrap_servers:
        logger.warning(
            "KAFKA_BOOTSTRAP_SERVERS is empty — outbox/shipment workers not started",
        )

    yield

    stop.set()
    for task in worker_tasks:
        task.cancel()
    if worker_tasks:
        await asyncio.gather(*worker_tasks, return_exceptions=True)
        logger.info("Kafka workers shut down")

    await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.include_router(health.router)
    app.include_router(orders.router)
    register_exception_handlers(app)

    return app
