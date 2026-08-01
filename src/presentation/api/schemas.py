from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from domain.entities import Order


class OrderCreateRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    item_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    quantity: int
    item_id: str
    status: str
    created_at: datetime
    update_at: datetime


class PaymentCallbackRequest(BaseModel):
    payment_id: str = Field(..., min_length=1)
    order_id: UUID
    status: str = Field(..., min_length=1)
    amount: str = Field(..., min_length=1)
    error_message: str | None = None


def order_to_response(order: Order) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        user_id=order.user_id,
        quantity=order.quantity,
        item_id=order.item_id,
        status=order.status.value,
        created_at=order.created_at,
        update_at=order.updated_at,
    )
