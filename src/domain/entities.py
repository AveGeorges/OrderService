from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class OrderStatus(StrEnum):
    NEW = "NEW"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class EventType(StrEnum):
    ORDER_PAID = "order.paid"
    ORDER_SHIPPED = "order.shipped"
    ORDER_CANCELLED = "order.cancelled"


@dataclass(slots=True)
class Order:
    id: UUID
    user_id: str
    item_id: str
    quantity: int
    status: OrderStatus
    idempotency_key: str
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )

    def mark_paid(self) -> None:
        self.status = OrderStatus.PAID
        self.updated_at = datetime.now(UTC)

    def mark_cancelled(self) -> None:
        self.status = OrderStatus.CANCELLED
        self.updated_at = datetime.now(UTC)

    def mark_shipped(self) -> None:
        self.status = OrderStatus.SHIPPED
        self.updated_at = datetime.now(UTC)


@dataclass(slots=True)
class OutboxEvent:
    event_type: str
    payload: dict[str, Any]
    id: UUID = field(default_factory=uuid4)
    status: OutboxStatus = OutboxStatus.PENDING
    retry_count: int = 0
    last_error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    sent_at: datetime | None = None


@dataclass(slots=True)
class InboxEvent:
    event_id: str
    event_type: str
    payload: dict[str, Any]
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = None
