
from __future__ import annotations

import logging
from uuid import UUID

from domain.entities import Order, OrderStatus, OutboxEvent

logger = logging.getLogger(__name__)

NOTIFICATION_EVENT_PREFIX = "notification."

_MESSAGES: dict[OrderStatus, str] = {
    OrderStatus.NEW: "NEW: Ваш заказ создан и ожидает оплаты",
    OrderStatus.PAID: "PAID: Ваш заказ успешно оплачен и готов к отправке",
    OrderStatus.SHIPPED: "SHIPPED: Ваш заказ отправлен в доставку",
    OrderStatus.CANCELLED: "CANCELLED: Ваш заказ отменен. Причина: {reason}",
}

_DEFAULT_CANCEL_REASON = "не указана"


def notification_message(
    status: OrderStatus,
    *,
    reason: str | None = None,
) -> str:
    template = _MESSAGES[status]
    if status == OrderStatus.CANCELLED:
        return template.format(reason=reason or _DEFAULT_CANCEL_REASON)
    return template


def notification_idempotency_key(order_id: UUID, status: OrderStatus) -> str:
    return f"{order_id}:{status.value}"


def notification_event_type(status: OrderStatus) -> str:
    return f"{NOTIFICATION_EVENT_PREFIX}{status.value}"


def is_notification_outbox_event(event_type: str) -> bool:
    return event_type.startswith(NOTIFICATION_EVENT_PREFIX)


def build_notification_outbox_event(
    order_id: UUID,
    user_id: str,
    status: OrderStatus,
    *,
    reason: str | None = None,
) -> OutboxEvent:
    return OutboxEvent(
        event_type=notification_event_type(status),
        payload={
            "user_id": user_id,
            "message": notification_message(status, reason=reason),
            "reference_id": str(order_id),
            "idempotency_key": notification_idempotency_key(order_id, status),
        },
    )


def build_notification_outbox_for_order(
    order: Order,
    status: OrderStatus | None = None,
    *,
    reason: str | None = None,
) -> OutboxEvent:
    target = status if status is not None else order.status
    return build_notification_outbox_event(
        order.id,
        order.user_id,
        target,
        reason=reason,
    )
