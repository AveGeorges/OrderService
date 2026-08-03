from collections.abc import Callable
from functools import lru_cache

from fastapi import Request

from application.ports.catalog import CatalogClient
from application.ports.payments import PaymentsClient
from application.ports.uow import UnitOfWork
from application.usecases.create_order import CreateOrder
from application.usecases.get_order import GetOrder
from application.usecases.process_payment_callback import ProcessPaymentCallback
from infrastructure.http.catalog import HttpCatalogClient
from infrastructure.http.payments import HttpPaymentsClient
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


def get_payments_client(request: Request) -> PaymentsClient:
    settings: Settings = request.app.state.settings
    return HttpPaymentsClient(
        base_url=settings.capashino_base_url,
        api_token=settings.api_token,
    )


def get_create_order_use_case(request: Request) -> CreateOrder:
    settings: Settings = request.app.state.settings
    return CreateOrder(
        uow_factory=get_uow_factory(request),
        catalog_client=get_catalog_client(request),
        payments_client=get_payments_client(request),
        payment_callback_url=settings.payment_callback_url,
    )


def get_get_order_use_case(request: Request) -> GetOrder:
    return GetOrder(uow_factory=get_uow_factory(request))


def get_process_payment_callback_use_case(
    request: Request,
) -> ProcessPaymentCallback:
    return ProcessPaymentCallback(uow_factory=get_uow_factory(request))
