from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from application.exceptions import CatalogServiceError
from domain.exceptions import (
    InsufficientStockError,
    ItemNotFoundError,
    OrderNotFoundError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(OrderNotFoundError)
    async def order_not_found_handler(
        _request: Request,
        exc: OrderNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ItemNotFoundError)
    async def item_not_found_handler(
        _request: Request,
        exc: ItemNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(InsufficientStockError)
    async def insufficient_stock_handler(
        _request: Request,
        exc: InsufficientStockError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(CatalogServiceError)
    async def catalog_service_handler(
        _request: Request,
        exc: CatalogServiceError,
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})
