"""Stage 4: notifications on status changes (best-effort, no outbox)."""

from decimal import Decimal

import pytest

from application.exceptions import NotificationsServiceError, PaymentsServiceError
from application.ports.catalog import CatalogItem
from application.services.order_notifications import OrderNotifier
from application.usecases.create_order import CreateOrder, CreateOrderCommand
from application.usecases.process_payment_callback import (
    PaymentCallbackCommand,
    ProcessPaymentCallback,
)
from application.usecases.process_shipment_event import (
    ProcessShipmentEvent,
    ShipmentEventCommand,
)
from domain.entities import EventType, OrderStatus
from tests.fakes import (
    FakeCatalogClient,
    FakeNotificationsClient,
    FakePaymentsClient,
    InMemoryUnitOfWork,
)

CALLBACK_URL = "http://order-service.svc:8000/api/orders/payment-callback"


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


async def test_notify_new_on_create() -> None:
    orders: dict = {}
    notifications = FakeNotificationsClient()
    order = await CreateOrder(
        uow_factory=lambda: InMemoryUnitOfWork(orders),
        catalog_client=_catalog(),
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
        notifier=OrderNotifier(notifications),
    )(
        CreateOrderCommand(
            user_id="u1",
            item_id="item-1",
            quantity=1,
            idempotency_key="n-new",
        ),
    )
    assert len(notifications.calls) == 1
    assert notifications.calls[0].idempotency_key == f"{order.id}:NEW"
    assert "создан" in notifications.calls[0].message


async def test_notify_paid_on_callback_once() -> None:
    orders: dict = {}
    notifications = FakeNotificationsClient()
    notifier = OrderNotifier(notifications)

    order = await CreateOrder(
        uow_factory=lambda: InMemoryUnitOfWork(orders),
        catalog_client=_catalog(),
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
        notifier=notifier,
    )(
        CreateOrderCommand(
            user_id="u1",
            item_id="item-1",
            quantity=1,
            idempotency_key="n-paid",
        ),
    )
    notifications.calls.clear()

    callback = ProcessPaymentCallback(
        lambda: InMemoryUnitOfWork(orders),
        notifier,
    )
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

    assert len(notifications.calls) == 1
    assert notifications.calls[0].idempotency_key == f"{order.id}:PAID"


async def test_notify_cancelled_on_payment_failed() -> None:
    orders: dict = {}
    notifications = FakeNotificationsClient()
    notifier = OrderNotifier(notifications)
    order = await CreateOrder(
        uow_factory=lambda: InMemoryUnitOfWork(orders),
        catalog_client=_catalog(),
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
        notifier=notifier,
    )(
        CreateOrderCommand(
            user_id="u1",
            item_id="item-1",
            quantity=1,
            idempotency_key="n-cancel",
        ),
    )
    notifications.calls.clear()

    await ProcessPaymentCallback(lambda: InMemoryUnitOfWork(orders), notifier)(
        PaymentCallbackCommand(
            payment_id="p2",
            order_id=order.id,
            status="failed",
            amount="10.00",
            error_message="card declined",
        ),
    )

    assert orders[order.id].status == OrderStatus.CANCELLED
    assert len(notifications.calls) == 1
    assert "card declined" in notifications.calls[0].message


async def test_notify_failure_does_not_break_create() -> None:
    orders: dict = {}
    notifications = FakeNotificationsClient(
        error=NotificationsServiceError("down"),
    )
    order = await CreateOrder(
        uow_factory=lambda: InMemoryUnitOfWork(orders),
        catalog_client=_catalog(),
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
        notifier=OrderNotifier(notifications),
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


async def test_notify_shipped_and_cancelled_from_shipping() -> None:
    orders: dict = {}
    notifications = FakeNotificationsClient()
    notifier = OrderNotifier(notifications)
    order = await CreateOrder(
        uow_factory=lambda: InMemoryUnitOfWork(orders),
        catalog_client=_catalog(),
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
        notifier=notifier,
    )(
        CreateOrderCommand(
            user_id="u1",
            item_id="item-1",
            quantity=1,
            idempotency_key="n-ship",
        ),
    )
    await ProcessPaymentCallback(lambda: InMemoryUnitOfWork(orders), notifier)(
        PaymentCallbackCommand(
            payment_id="p1",
            order_id=order.id,
            status="succeeded",
            amount="10.00",
        ),
    )
    notifications.calls.clear()

    await ProcessShipmentEvent(
        lambda: InMemoryUnitOfWork(orders),
        notifier,
    )(
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
    assert notifications.calls[0].idempotency_key == f"{order.id}:SHIPPED"


@pytest.mark.asyncio
async def test_payment_create_fail_notifies_cancelled() -> None:
    orders: dict = {}
    notifications = FakeNotificationsClient()
    with pytest.raises(PaymentsServiceError):
        await CreateOrder(
            uow_factory=lambda: InMemoryUnitOfWork(orders),
            catalog_client=_catalog(),
            payments_client=FakePaymentsClient(error=PaymentsServiceError("x")),
            payment_callback_url=CALLBACK_URL,
            notifier=OrderNotifier(notifications),
        )(
            CreateOrderCommand(
                user_id="u1",
                item_id="item-1",
                quantity=1,
                idempotency_key="n-pay-fail",
            ),
        )
    keys = [c.idempotency_key for c in notifications.calls]
    assert any(k.endswith(":NEW") for k in keys)
    assert any(k.endswith(":CANCELLED") for k in keys)
