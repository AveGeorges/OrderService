import logging
from decimal import Decimal

import httpx

from application.exceptions import CatalogServiceError
from application.ports.catalog import CatalogClient, CatalogItem
from domain.exceptions import ItemNotFoundError

logger = logging.getLogger(__name__)


class HttpCatalogClient(CatalogClient):
    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._client = client
        self._timeout = timeout

    async def get_item(self, item_id: str) -> CatalogItem:
        url = f"{self._base_url}/api/catalog/items/{item_id}"
        headers = {"X-API-Key": self._api_token}

        try:
            if self._client is not None:
                response = await self._client.get(url, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.exception("Catalog request failed for item_id=%s", item_id)
            raise CatalogServiceError("Catalog service unavailable") from exc

        if response.status_code == 404:
            raise ItemNotFoundError(item_id)

        if response.status_code >= 400:
            logger.error(
                "Catalog error status=%s item_id=%s body=%s",
                response.status_code,
                item_id,
                response.text,
            )
            raise CatalogServiceError(
                f"Catalog service returned status {response.status_code}",
            )

        data = response.json()
        return CatalogItem(
            id=str(data["id"]),
            name=str(data["name"]),
            price=Decimal(str(data["price"])),
            available_qty=int(data["available_qty"]),
        )
