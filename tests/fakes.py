from types import TracebackType
from typing import Self
from uuid import UUID

from application.ports.catalog import CatalogClient, CatalogItem
from application.ports.inbox import InboxRepository
from application.ports.messaging import EventPublisher
from application.ports.notifications import (
    Notification,
    NotificationsClient,
    SendNotificationRequest,
)
from application.ports.outbox import OutboxRepository
from application.ports.payments import CreatePaymentRequest, Payment, PaymentsClient
from application.ports.repositories import OrderRepository
from application.ports.uow import UnitOfWork
from domain.entities import InboxEvent, Order, OutboxEvent, OutboxStatus
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


class InMemoryOutboxRepository(OutboxRepository):
    def __init__(self, storage: dict[UUID, OutboxEvent]) -> None:
        self._storage = storage

    async def add(self, event: OutboxEvent) -> OutboxEvent:
        self._storage[event.id] = event
        return event

    async def get_pending_for_update(self, limit: int = 100) -> list[OutboxEvent]:
        pending = [
            event
            for event in self._storage.values()
            if event.status == OutboxStatus.PENDING
        ]
        pending.sort(key=lambda event: event.created_at)
        return pending[:limit]

    async def mark_as_sent(self, event_id: UUID) -> None:
        event = self._storage[event_id]
        event.status = OutboxStatus.SENT

    async def mark_as_failed(
        self,
        event_id: UUID,
        error: str,
        *,
        max_retries: int = 5,
    ) -> None:
        event = self._storage[event_id]
        event.retry_count += 1
        event.last_error = error
        if event.retry_count >= max_retries:
            event.status = OutboxStatus.FAILED


class InMemoryInboxRepository(InboxRepository):
    def __init__(self, storage: dict[str, InboxEvent]) -> None:
        self._storage = storage

    async def add(self, event: InboxEvent) -> InboxEvent | None:
        if event.event_id in self._storage:
            return None
        self._storage[event.event_id] = event
        return event

    async def exists(self, event_id: str) -> bool:
        return event_id in self._storage


class InMemoryUnitOfWork(UnitOfWork):
    def __init__(
        self,
        orders: dict[UUID, Order] | None = None,
        outbox: dict[UUID, OutboxEvent] | None = None,
        inbox: dict[str, InboxEvent] | None = None,
    ) -> None:
        self._orders = orders if orders is not None else {}
        self._outbox = outbox if outbox is not None else {}
        self._inbox = inbox if inbox is not None else {}
        self.orders = InMemoryOrderRepository(self._orders)
        self.outbox = InMemoryOutboxRepository(self._outbox)
        self.inbox = InMemoryInboxRepository(self._inbox)
        self.committed = False

    async def __aenter__(self) -> Self:
        self.orders = InMemoryOrderRepository(self._orders)
        self.outbox = InMemoryOutboxRepository(self._outbox)
        self.inbox = InMemoryInboxRepository(self._inbox)
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
            user_id="user-1",
            order_id=str(request.order_id),
            amount=request.amount,
            status="pending",
            idempotency_key=request.idempotency_key,
            created_at="2024-01-01T00:00:00Z",
        )


class FakeNotificationsClient(NotificationsClient):
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.calls: list[SendNotificationRequest] = []

    async def send(self, request: SendNotificationRequest) -> Notification:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return Notification(
            id="notification-1",
            user_id="user-1",
            message=request.message,
            reference_id=request.reference_id,
        )


class FakeEventPublisher(EventPublisher):
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.started = False
        self.stopped = False
        self.calls: list[tuple[str, str, dict]] = []

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def publish(
        self,
        topic: str,
        *,
        key: str,
        payload: dict,
    ) -> None:
        if self._error is not None:
            raise self._error
        self.calls.append((topic, key, payload))
