from types import TracebackType
from typing import Self
from uuid import UUID

from application.ports.catalog import CatalogClient, CatalogItem
from application.ports.payments import CreatePaymentRequest, Payment, PaymentsClient
from application.ports.repositories import OrderRepository
from application.ports.uow import UnitOfWork
from domain.entities import Order
from domain.exceptions import ItemNotFoundError


class InMemoryOrderRepository(OrderRepository):
    def __init__(self, storage: dict[UUID, Order]) -> None:
        self._storage = storage

    async def add(self, order: Order) -> Order:
        self._storage[order.id] = order
        return order

    async def get_by_id(self, order_id: UUID) -> Order | None:
        return self._storage.get(order_id)

    async def get_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        for order in self._storage.values():
            if order.idempotency_key == idempotency_key:
                return order
        return None

    async def update(self, order: Order) -> Order:
        self._storage[order.id] = order
        return order


class InMemoryUnitOfWork(UnitOfWork):
    def __init__(self, storage: dict[UUID, Order]) -> None:
        self._storage = storage
        self.orders = InMemoryOrderRepository(storage)
        self.committed = False

    async def __aenter__(self) -> Self:
        self.orders = InMemoryOrderRepository(self._storage)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.committed = False


class FakeCatalogClient(CatalogClient):
    def __init__(
        self,
        items: dict[str, CatalogItem] | None = None,
        *,
        missing_ids: set[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._items = items or {}
        self._missing_ids = missing_ids or set()
        self._error = error
        self.calls: list[str] = []

    async def get_item(self, item_id: str) -> CatalogItem:
        self.calls.append(item_id)
        if self._error is not None:
            raise self._error
        if item_id in self._missing_ids or item_id not in self._items:
            raise ItemNotFoundError(item_id)
        return self._items[item_id]


class FakePaymentsClient(PaymentsClient):
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.calls: list[CreatePaymentRequest] = []

    async def create_payment(self, request: CreatePaymentRequest) -> Payment:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return Payment(
            id="payment-1",
            order_id=str(request.order_id),
            amount=request.amount,
            status="pending",
            idempotency_key=request.idempotency_key,
        )
