from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CatalogItem:
    id: str
    name: str
    price: Decimal
    available_qty: int


class CatalogClient(ABC):
    @abstractmethod
    async def get_item(self, item_id: str) -> CatalogItem:
        """Fetch item by id. Raises ItemNotFoundError if missing."""
        raise NotImplementedError
