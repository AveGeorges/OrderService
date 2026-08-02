"""Best-effort order status notifications (no outbox)."""

from __future__ import annotations

import logging
from uuid import UUID

from application.ports.notifications import (
    NotificationsClient,
    SendNotificationRequest,
)
from domain.entities import Order, OrderStatus

logger = logging.getLogger(__name__)

_MESSAGES: dict[OrderStatus, str] = {
    OrderStatus.NEW: "Ваш заказ создан и ожидает оплаты",
    OrderStatus.PAID: "Ваш заказ успешно оплачен и готов к отправке",
    OrderStatus.SHIPPED: "Ваш заказ отправлен в доставку",
    OrderStatus.CANCELLED: "Ваш заказ отменен. Причина: {reason}",
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


class OrderNotifier:
    """Sends status notifications without failing the main order flow."""

    def __init__(self, client: NotificationsClient) -> None:
        self._client = client

    async def notify_status(
        self,
        order_id: UUID,
        status: OrderStatus,
        *,
        reason: str | None = None,
    ) -> bool:
        """Return True if sent, False if Notifications failed (logged)."""
        request = SendNotificationRequest(
            message=notification_message(status, reason=reason),
            reference_id=str(order_id),
            idempotency_key=notification_idempotency_key(order_id, status),
        )
        try:
            await self._client.send(request)
        except Exception:
            logger.exception(
                "Failed to send notification order_id=%s status=%s key=%s",
                order_id,
                status.value,
                request.idempotency_key,
            )
            return False

        logger.info(
            "Notification sent order_id=%s status=%s key=%s",
            order_id,
            status.value,
            request.idempotency_key,
        )
        return True

    async def notify_order(
        self,
        order: Order,
        status: OrderStatus | None = None,
        *,
        reason: str | None = None,
    ) -> bool:
        target = status if status is not None else order.status
        return await self.notify_status(order.id, target, reason=reason)
