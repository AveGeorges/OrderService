"""Catalog Service HTTP client — implemented in stage 1."""

from application.ports.catalog import CatalogClient, CatalogItem


class HttpCatalogClient(CatalogClient):
    def __init__(self, base_url: str, api_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token

    async def get_item(self, item_id: str) -> CatalogItem:
        raise NotImplementedError("Catalog client will be implemented in stage 1")
