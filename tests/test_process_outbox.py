from application.exceptions import NotificationsServiceError
from application.services.order_notifications import (
    build_notification_outbox_event,
    notification_event_type,
)
from application.usecases.process_outbox_events import ProcessOutboxEvents
from domain.entities import EventType, OrderStatus, OutboxEvent, OutboxStatus
from tests.fakes import FakeEventPublisher, FakeNotificationsClient, InMemoryUnitOfWork

TOPIC = "student_system-order.events"


def _make_event(order_id: str = "order-1") -> OutboxEvent:
    return OutboxEvent(
        event_type=EventType.ORDER_PAID,
        payload={
            "event_type": EventType.ORDER_PAID,
            "order_id": order_id,
            "item_id": "item-1",
            "quantity": 1,
            "idempotency_key": "key-1",
        },
    )


def _process(
    outbox: dict,
    *,
    publisher: FakeEventPublisher | None = None,
    notifications: FakeNotificationsClient | None = None,
    **kwargs: object,
) -> ProcessOutboxEvents:
    return ProcessOutboxEvents(
        uow_factory=lambda: InMemoryUnitOfWork(outbox=outbox),
        publisher=publisher or FakeEventPublisher(),
        notifications=notifications or FakeNotificationsClient(),
        topic=TOPIC,
        **kwargs,  # type: ignore[arg-type]
    )


async def test_process_outbox_publishes_and_marks_sent() -> None:
    outbox: dict = {}
    event = _make_event()
    outbox[event.id] = event
    publisher = FakeEventPublisher()

    processed = await _process(outbox, publisher=publisher)()

    assert processed == 1
    assert len(publisher.calls) == 1
    topic, key, payload = publisher.calls[0]
    assert topic == TOPIC
    assert key == "order-1"
    assert payload["event_type"] == EventType.ORDER_PAID
    assert outbox[event.id].status == OutboxStatus.SENT


async def test_process_outbox_empty_batch() -> None:
    publisher = FakeEventPublisher()
    processed = await _process({}, publisher=publisher)()
    assert processed == 0
    assert publisher.calls == []


async def test_process_outbox_keeps_pending_until_max_retries() -> None:
    outbox: dict = {}
    event = _make_event()
    outbox[event.id] = event
    publisher = FakeEventPublisher(error=RuntimeError("broker down"))

    process = _process(outbox, publisher=publisher, max_retries=3)

    await process()
    assert outbox[event.id].status == OutboxStatus.PENDING
    assert outbox[event.id].retry_count == 1
    assert "broker down" in (outbox[event.id].last_error or "")

    await process()
    assert outbox[event.id].status == OutboxStatus.PENDING
    assert outbox[event.id].retry_count == 2

    await process()
    assert outbox[event.id].status == OutboxStatus.FAILED
    assert outbox[event.id].retry_count == 3


async def test_process_outbox_sends_notification_with_retries() -> None:
    from uuid import uuid4

    outbox: dict = {}
    order_id = uuid4()
    event = build_notification_outbox_event(
        order_id,
        "user-1",
        OrderStatus.NEW,
    )
    outbox[event.id] = event
    notifications = FakeNotificationsClient(
        error=NotificationsServiceError("down"),
        fail_times=2,
    )

    processed = await _process(
        outbox,
        notifications=notifications,
        notify_attempts=3,
        notify_retry_delay_seconds=0,
    )()

    assert processed == 1
    assert outbox[event.id].status == OutboxStatus.SENT
    assert len(notifications.calls) == 3
    assert notifications.calls[0].idempotency_key == f"{order_id}:NEW"
    assert event.event_type == notification_event_type(OrderStatus.NEW)


async def test_process_outbox_notification_exhausts_send_retries() -> None:
    from uuid import uuid4

    outbox: dict = {}
    event = build_notification_outbox_event(
        uuid4(),
        "user-1",
        OrderStatus.PAID,
    )
    outbox[event.id] = event
    notifications = FakeNotificationsClient(
        error=NotificationsServiceError("down"),
    )

    await _process(
        outbox,
        notifications=notifications,
        notify_attempts=3,
        notify_retry_delay_seconds=0,
        max_retries=2,
    )()

    assert outbox[event.id].status == OutboxStatus.PENDING
    assert outbox[event.id].retry_count == 1
    assert len(notifications.calls) == 3
