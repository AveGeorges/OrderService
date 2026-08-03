"""Stage 4: notifications via outbox + send-time retries."""

from decimal import Decimal
from uuid import UUID

import pytest

from application.exceptions import NotificationsServiceError, PaymentsServiceError
from application.ports.catalog import CatalogItem
from application.services.order_notifications import is_notification_outbox_event
from application.usecases.create_order import CreateOrder, CreateOrderCommand
from application.usecases.process_outbox_events import ProcessOutboxEvents
from application.usecases.process_payment_callback import (
    PaymentCallbackCommand,
    ProcessPaymentCallback,
)
from application.usecases.process_shipment_event import (
    ProcessShipmentEvent,
    ShipmentEventCommand,
)
from domain.entities import EventType, OrderStatus, OutboxEvent, OutboxStatus
from tests.fakes import (
    FakeCatalogClient,
    FakeEventPublisher,
    FakeNotificationsClient,
    FakePaymentsClient,
    InMemoryUnitOfWork,
)

CALLBACK_URL = "http://order-service.svc:8000/api/orders/payment-callback"
TOPIC = "student_system-order.events"


def _catalog() -> FakeCatalogClient:
    return FakeCatalogClient(
        {
            "item-1": CatalogItem(
                id="item-1",
                name="Product",
                price=Decimal("10.00"),
                available_qty=5,
            ),
        },
    )


def _uow(orders: dict, outbox: dict, inbox: dict | None = None):
    def factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(orders, outbox, inbox or {})

    return factory


async def _flush_outbox(
    orders: dict,
    outbox: dict,
    notifications: FakeNotificationsClient,
) -> int:
    return await ProcessOutboxEvents(
        uow_factory=_uow(orders, outbox),
        publisher=FakeEventPublisher(),
        notifications=notifications,
        topic=TOPIC,
        notify_attempts=3,
        notify_retry_delay_seconds=0,
    )()


def _notification_events(outbox: dict[UUID, OutboxEvent]) -> list[OutboxEvent]:
    return [e for e in outbox.values() if is_notification_outbox_event(e.event_type)]


async def test_notify_new_on_create() -> None:
    orders: dict = {}
    outbox: dict = {}
    notifications = FakeNotificationsClient()
    order = await CreateOrder(
        uow_factory=_uow(orders, outbox),
        catalog_client=_catalog(),
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
    )(
        CreateOrderCommand(
            user_id="u1",
            item_id="item-1",
            quantity=1,
            idempotency_key="n-new",
        ),
    )
    events = _notification_events(outbox)
    assert len(events) == 1
    assert events[0].payload["idempotency_key"] == f"{order.id}:NEW"
    assert "NEW" in events[0].payload["message"]

    await _flush_outbox(orders, outbox, notifications)
    assert len(notifications.calls) == 1
    assert notifications.calls[0].user_id == "u1"
    assert events[0].status == OutboxStatus.SENT


async def test_notify_paid_on_callback_once() -> None:
    orders: dict = {}
    outbox: dict = {}
    notifications = FakeNotificationsClient()
    uow = _uow(orders, outbox)

    order = await CreateOrder(
        uow_factory=uow,
        catalog_client=_catalog(),
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
    )(
        CreateOrderCommand(
            user_id="u1",
            item_id="item-1",
            quantity=1,
            idempotency_key="n-paid",
        ),
    )
    await _flush_outbox(orders, outbox, notifications)
    notifications.calls.clear()

    callback = ProcessPaymentCallback(uow)
    await callback(
        PaymentCallbackCommand(
            payment_id="p1",
            order_id=order.id,
            status="succeeded",
            amount="10.00",
        ),
    )
    await callback(
        PaymentCallbackCommand(
            payment_id="p1",
            order_id=order.id,
            status="succeeded",
            amount="10.00",
        ),
    )

    paid_events = [
        e
        for e in _notification_events(outbox)
        if e.payload["idempotency_key"] == f"{order.id}:PAID"
    ]
    assert len(paid_events) == 1

    await _flush_outbox(orders, outbox, notifications)
    assert len(notifications.calls) == 1
    assert "PAID" in notifications.calls[0].message


async def test_notify_cancelled_on_payment_failed() -> None:
    orders: dict = {}
    outbox: dict = {}
    notifications = FakeNotificationsClient()
    uow = _uow(orders, outbox)
    order = await CreateOrder(
        uow_factory=uow,
        catalog_client=_catalog(),
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
    )(
        CreateOrderCommand(
            user_id="u1",
            item_id="item-1",
            quantity=1,
            idempotency_key="n-cancel",
        ),
    )
    await _flush_outbox(orders, outbox, notifications)
    notifications.calls.clear()

    await ProcessPaymentCallback(uow)(
        PaymentCallbackCommand(
            payment_id="p2",
            order_id=order.id,
            status="failed",
            amount="10.00",
            error_message="card declined",
        ),
    )

    assert orders[order.id].status == OrderStatus.CANCELLED
    cancelled = [
        e
        for e in _notification_events(outbox)
        if e.payload["idempotency_key"].endswith(":CANCELLED")
    ]
    assert len(cancelled) == 1
    assert "card declined" in cancelled[0].payload["message"]

    await _flush_outbox(orders, outbox, notifications)
    assert len(notifications.calls) == 1


async def test_notify_enqueue_does_not_break_create_when_send_fails() -> None:
    orders: dict = {}
    outbox: dict = {}
    notifications = FakeNotificationsClient(
        error=NotificationsServiceError("down"),
    )
    order = await CreateOrder(
        uow_factory=_uow(orders, outbox),
        catalog_client=_catalog(),
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
    )(
        CreateOrderCommand(
            user_id="u1",
            item_id="item-1",
            quantity=1,
            idempotency_key="n-fail",
        ),
    )
    assert order.status == OrderStatus.NEW
    assert order.id in orders
    assert len(_notification_events(outbox)) == 1

    await _flush_outbox(orders, outbox, notifications)
    assert outbox[next(iter(outbox))].status == OutboxStatus.PENDING


async def test_notify_shipped_and_cancelled_from_shipping() -> None:
    orders: dict = {}
    outbox: dict = {}
    inbox: dict = {}
    notifications = FakeNotificationsClient()
    uow = _uow(orders, outbox, inbox)
    order = await CreateOrder(
        uow_factory=uow,
        catalog_client=_catalog(),
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
    )(
        CreateOrderCommand(
            user_id="u1",
            item_id="item-1",
            quantity=1,
            idempotency_key="n-ship",
        ),
    )
    await ProcessPaymentCallback(uow)(
        PaymentCallbackCommand(
            payment_id="p1",
            order_id=order.id,
            status="succeeded",
            amount="10.00",
        ),
    )
    await _flush_outbox(orders, outbox, notifications)
    notifications.calls.clear()

    await ProcessShipmentEvent(uow)(
        ShipmentEventCommand(
            event_id="ship-1",
            event_type=EventType.ORDER_SHIPPED,
            order_id=order.id,
            payload={
                "event_type": EventType.ORDER_SHIPPED,
                "order_id": str(order.id),
                "shipment_id": "s1",
            },
        ),
    )
    assert orders[order.id].status == OrderStatus.SHIPPED
    shipped = [
        e
        for e in _notification_events(outbox)
        if e.payload["idempotency_key"] == f"{order.id}:SHIPPED"
    ]
    assert len(shipped) == 1

    await _flush_outbox(orders, outbox, notifications)
    assert notifications.calls[0].idempotency_key == f"{order.id}:SHIPPED"
    assert "SHIPPED" in notifications.calls[0].message


@pytest.mark.asyncio
async def test_payment_create_fail_enqueues_cancelled() -> None:
    orders: dict = {}
    outbox: dict = {}
    with pytest.raises(PaymentsServiceError):
        await CreateOrder(
            uow_factory=_uow(orders, outbox),
            catalog_client=_catalog(),
            payments_client=FakePaymentsClient(error=PaymentsServiceError("x")),
            payment_callback_url=CALLBACK_URL,
        )(
            CreateOrderCommand(
                user_id="u1",
                item_id="item-1",
                quantity=1,
                idempotency_key="n-pay-fail",
            ),
        )
    keys = [e.payload["idempotency_key"] for e in _notification_events(outbox)]
    assert any(k.endswith(":NEW") for k in keys)
    assert any(k.endswith(":CANCELLED") for k in keys)
