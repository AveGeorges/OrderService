from uuid import uuid4

from application.services.order_notifications import (
    build_notification_outbox_event,
    is_notification_outbox_event,
    notification_event_type,
    notification_idempotency_key,
    notification_message,
)
from domain.entities import OrderStatus, OutboxStatus


def test_notification_messages() -> None:
    assert notification_message(OrderStatus.NEW) == (
        "NEW: Ваш заказ создан и ожидает оплаты"
    )
    assert notification_message(OrderStatus.PAID) == (
        "PAID: Ваш заказ успешно оплачен и готов к отправке"
    )
    assert notification_message(OrderStatus.SHIPPED) == (
        "SHIPPED: Ваш заказ отправлен в доставку"
    )
    assert notification_message(OrderStatus.CANCELLED, reason="нет товара") == (
        "CANCELLED: Ваш заказ отменен. Причина: нет товара"
    )
    assert notification_message(OrderStatus.CANCELLED) == (
        "CANCELLED: Ваш заказ отменен. Причина: не указана"
    )


def test_idempotency_key_stable() -> None:
    order_id = uuid4()
    assert (
        notification_idempotency_key(order_id, OrderStatus.PAID) == f"{order_id}:PAID"
    )


def test_build_notification_outbox_event() -> None:
    order_id = uuid4()
    event = build_notification_outbox_event(
        order_id,
        "user-1",
        OrderStatus.NEW,
    )
    assert event.event_type == notification_event_type(OrderStatus.NEW)
    assert is_notification_outbox_event(event.event_type)
    assert event.status == OutboxStatus.PENDING
    assert event.payload == {
        "user_id": "user-1",
        "message": "NEW: Ваш заказ создан и ожидает оплаты",
        "reference_id": str(order_id),
        "idempotency_key": f"{order_id}:NEW",
    }
