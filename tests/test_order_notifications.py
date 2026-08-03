from uuid import uuid4

import pytest

from application.exceptions import NotificationsServiceError
from application.services.order_notifications import (
    OrderNotifier,
    notification_idempotency_key,
    notification_message,
)
from domain.entities import OrderStatus
from tests.fakes import FakeNotificationsClient


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


@pytest.mark.asyncio
async def test_notifier_sends_request() -> None:
    client = FakeNotificationsClient()
    notifier = OrderNotifier(client)
    order_id = uuid4()

    ok = await notifier.notify_status(
        order_id,
        OrderStatus.NEW,
        user_id="user-1",
    )

    assert ok is True
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call.user_id == "user-1"
    assert call.reference_id == str(order_id)
    assert call.idempotency_key == f"{order_id}:NEW"
    assert call.message == "NEW: Ваш заказ создан и ожидает оплаты"


@pytest.mark.asyncio
async def test_notifier_swallows_errors() -> None:
    client = FakeNotificationsClient(
        error=NotificationsServiceError("down"),
    )
    notifier = OrderNotifier(client)

    ok = await notifier.notify_status(
        uuid4(),
        OrderStatus.PAID,
        user_id="user-1",
    )

    assert ok is False
    assert len(client.calls) == 1
