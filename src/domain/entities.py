from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class OrderStatus(StrEnum):
    NEW = "NEW"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"


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
