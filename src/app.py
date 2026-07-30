import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from infrastructure.persistence.database import create_engine, create_session_factory
from infrastructure.persistence.models import Base
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

    yield

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

    return app
