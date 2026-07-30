from abc import ABC, abstractmethod
from uuid import UUID

from domain.entities import Order


class OrderRepository(ABC):
    @abstractmethod
    async def add(self, order: Order) -> Order:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, order_id: UUID) -> Order | None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        raise NotImplementedError

    @abstractmethod
    async def update(self, order: Order) -> Order:
        raise NotImplementedError
