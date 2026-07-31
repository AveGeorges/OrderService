from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from application.exceptions import CatalogServiceError
from application.ports.catalog import CatalogItem
from domain.exceptions import ItemNotFoundError
from infrastructure.http.catalog import HttpCatalogClient


@pytest.mark.asyncio
async def test_http_catalog_get_item_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "token"
        assert request.url.path.endswith("/api/catalog/items/item-1")
        return httpx.Response(
            200,
            json={
                "id": "item-1",
                "name": "Product",
                "price": "100.00",
                "available_qty": 10,
                "created_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        catalog = HttpCatalogClient(
            base_url="https://capashino.test",
            api_token="token",
            client=client,
        )
        item = await catalog.get_item("item-1")

    assert item == CatalogItem(
        id="item-1",
        name="Product",
        price=Decimal("100.00"),
        available_qty=10,
    )


@pytest.mark.asyncio
async def test_http_catalog_item_not_found() -> None:
    transport = httpx.MockTransport(lambda _r: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        catalog = HttpCatalogClient("https://capashino.test", "token", client=client)
        with pytest.raises(ItemNotFoundError):
            await catalog.get_item("missing")


@pytest.mark.asyncio
async def test_http_catalog_server_error() -> None:
    transport = httpx.MockTransport(lambda _r: httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(transport=transport) as client:
        catalog = HttpCatalogClient("https://capashino.test", "token", client=client)
        with pytest.raises(CatalogServiceError):
            await catalog.get_item(str(uuid4()))
