"""Stage 3 checklist: outbox + inbox flows end-to-end (in-memory)."""

from decimal import Decimal
from uuid import uuid4

from application.ports.catalog import CatalogItem
from application.services.order_notifications import OrderNotifier
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
from domain.entities import EventType, OrderStatus, OutboxStatus
from tests.fakes import (
    FakeCatalogClient,
    FakeEventPublisher,
    FakeNotificationsClient,
    FakePaymentsClient,
    InMemoryUnitOfWork,
)

CALLBACK_URL = "http://order-service.svc:8000/api/orders/payment-callback"
TOPIC = "student_system-order.events"


def _notifier() -> OrderNotifier:
    return OrderNotifier(FakeNotificationsClient())


async def _new_paid_order(
    orders: dict,
    outbox: dict,
    *,
    idempotency_key: str = "stage3-key",
):
    def uow_factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(orders, outbox)

    catalog = FakeCatalogClient(
        {
            "item-1": CatalogItem(
                id="item-1",
                name="Product",
                price=Decimal("10.00"),
                available_qty=5,
            ),
        },
    )
    notifier = _notifier()
    order = await CreateOrder(
        uow_factory=uow_factory,
        catalog_client=catalog,
        payments_client=FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
        notifier=notifier,
    )(
        CreateOrderCommand(
            user_id="user-1",
            item_id="item-1",
            quantity=1,
            idempotency_key=idempotency_key,
        ),
    )
    await ProcessPaymentCallback(uow_factory, notifier)(
        PaymentCallbackCommand(
            payment_id="pay-1",
            order_id=order.id,
            status="succeeded",
            amount="10.00",
        ),
    )
    return order


async def test_f1_first_paid_writes_single_outbox_order_paid() -> None:
    orders: dict = {}
    outbox: dict = {}
    order = await _new_paid_order(orders, outbox)

    assert orders[order.id].status == OrderStatus.PAID
    assert len(outbox) == 1
    event = next(iter(outbox.values()))
    assert event.event_type == EventType.ORDER_PAID
    assert event.status == OutboxStatus.PENDING
    assert event.payload["order_id"] == str(order.id)


async def test_f2_repeat_callback_does_not_duplicate_outbox() -> None:
    orders: dict = {}
    outbox: dict = {}
    order = await _new_paid_order(orders, outbox, idempotency_key="stage3-dup")

    def uow_factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(orders, outbox)

    await ProcessPaymentCallback(uow_factory, _notifier())(
        PaymentCallbackCommand(
            payment_id="pay-1",
            order_id=order.id,
            status="succeeded",
            amount="10.00",
        ),
    )
    assert len(outbox) == 1


async def test_f3_outbox_worker_marks_sent() -> None:
    orders: dict = {}
    outbox: dict = {}
    order = await _new_paid_order(orders, outbox, idempotency_key="stage3-sent")
    publisher = FakeEventPublisher()

    processed = await ProcessOutboxEvents(
        uow_factory=lambda: InMemoryUnitOfWork(orders, outbox),
        publisher=publisher,
        topic=TOPIC,
    )()

    assert processed == 1
    event = next(iter(outbox.values()))
    assert event.status == OutboxStatus.SENT
    assert publisher.calls[0][1] == str(order.id)


async def test_f4_publish_error_keeps_pending_and_increments_retry() -> None:
    orders: dict = {}
    outbox: dict = {}
    await _new_paid_order(orders, outbox, idempotency_key="stage3-retry")
    publisher = FakeEventPublisher(error=RuntimeError("kafka unavailable"))

    await ProcessOutboxEvents(
        uow_factory=lambda: InMemoryUnitOfWork(orders, outbox),
        publisher=publisher,
        topic=TOPIC,
        max_retries=5,
    )()

    event = next(iter(outbox.values()))
    assert event.status == OutboxStatus.PENDING
    assert event.retry_count == 1
    assert "kafka unavailable" in (event.last_error or "")


async def test_f5_shipped_then_repeat_is_noop() -> None:
    orders: dict = {}
    outbox: dict = {}
    inbox: dict = {}
    order = await _new_paid_order(orders, outbox, idempotency_key="stage3-ship")

    process = ProcessShipmentEvent(
        lambda: InMemoryUnitOfWork(orders, outbox, inbox),
        _notifier(),
    )
    command = ShipmentEventCommand(
        event_id="evt-ship-1",
        event_type=EventType.ORDER_SHIPPED,
        order_id=order.id,
        payload={
            "event_type": EventType.ORDER_SHIPPED,
            "order_id": str(order.id),
            "shipment_id": "shp-1",
        },
    )

    assert await process(command) is True
    assert orders[order.id].status == OrderStatus.SHIPPED
    assert await process(command) is False
    assert len(inbox) == 1


async def test_f6_cancelled_then_repeat_is_noop() -> None:
    orders: dict = {}
    outbox: dict = {}
    inbox: dict = {}
    order = await _new_paid_order(orders, outbox, idempotency_key="stage3-cancel")

    process = ProcessShipmentEvent(
        lambda: InMemoryUnitOfWork(orders, outbox, inbox),
        _notifier(),
    )
    command = ShipmentEventCommand(
        event_id="evt-cancel-1",
        event_type=EventType.ORDER_CANCELLED,
        order_id=order.id,
        payload={
            "event_type": EventType.ORDER_CANCELLED,
            "order_id": str(order.id),
            "reason": "warehouse reject",
        },
    )

    assert await process(command) is True
    assert orders[order.id].status == OrderStatus.CANCELLED
    assert await process(command) is False
    assert len(inbox) == 1


async def test_full_path_paid_outbox_publish_then_shipped() -> None:
    orders: dict = {}
    outbox: dict = {}
    inbox: dict = {}
    order = await _new_paid_order(orders, outbox, idempotency_key="stage3-full")

    publisher = FakeEventPublisher()
    await ProcessOutboxEvents(
        uow_factory=lambda: InMemoryUnitOfWork(orders, outbox, inbox),
        publisher=publisher,
        topic=TOPIC,
    )()
    assert next(iter(outbox.values())).status == OutboxStatus.SENT

    await ProcessShipmentEvent(
        lambda: InMemoryUnitOfWork(orders, outbox, inbox),
        _notifier(),
    )(
        ShipmentEventCommand(
            event_id=f"ship-{uuid4()}",
            event_type=EventType.ORDER_SHIPPED,
            order_id=order.id,
            payload={
                "event_type": EventType.ORDER_SHIPPED,
                "order_id": str(order.id),
                "shipment_id": "shp-full",
            },
        ),
    )
    assert orders[order.id].status == OrderStatus.SHIPPED
