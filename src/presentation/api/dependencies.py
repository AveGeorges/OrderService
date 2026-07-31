from collections.abc import Callable
from functools import lru_cache

from fastapi import Request

from application.ports.catalog import CatalogClient
from application.ports.uow import UnitOfWork
from application.usecases.create_order import CreateOrder
from application.usecases.get_order import GetOrder
from infrastructure.http.catalog import HttpCatalogClient
from infrastructure.persistence.uow import SQLAlchemyUnitOfWork
from settings import Settings, get_settings


@lru_cache
def get_app_settings() -> Settings:
    return get_settings()


def get_uow_factory(request: Request) -> Callable[[], UnitOfWork]:
    session_factory = request.app.state.session_factory

    def factory() -> UnitOfWork:
        return SQLAlchemyUnitOfWork(session_factory)

    return factory


def get_catalog_client(request: Request) -> CatalogClient:
    settings: Settings = request.app.state.settings
    return HttpCatalogClient(
        base_url=settings.capashino_base_url,
        api_token=settings.api_token,
    )


def get_create_order_use_case(
    request: Request,
) -> CreateOrder:
    return CreateOrder(
        uow_factory=get_uow_factory(request),
        catalog_client=get_catalog_client(request),
    )


def get_get_order_use_case(request: Request) -> GetOrder:
    return GetOrder(uow_factory=get_uow_factory(request))
