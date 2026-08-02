from application.usecases.process_outbox_events import ProcessOutboxEvents
from domain.entities import EventType, OutboxEvent, OutboxStatus
from tests.fakes import FakeEventPublisher, InMemoryUnitOfWork

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


async def test_process_outbox_publishes_and_marks_sent() -> None:
    outbox: dict = {}
    event = _make_event()
    outbox[event.id] = event
    publisher = FakeEventPublisher()

    processed = await ProcessOutboxEvents(
        uow_factory=lambda: InMemoryUnitOfWork(outbox=outbox),
        publisher=publisher,
        topic=TOPIC,
    )()

    assert processed == 1
    assert len(publisher.calls) == 1
    topic, key, payload = publisher.calls[0]
    assert topic == TOPIC
    assert key == "order-1"
    assert payload["event_type"] == EventType.ORDER_PAID
    assert outbox[event.id].status == OutboxStatus.SENT


async def test_process_outbox_empty_batch() -> None:
    publisher = FakeEventPublisher()
    processed = await ProcessOutboxEvents(
        uow_factory=lambda: InMemoryUnitOfWork(),
        publisher=publisher,
        topic=TOPIC,
    )()
    assert processed == 0
    assert publisher.calls == []


async def test_process_outbox_keeps_pending_until_max_retries() -> None:
    outbox: dict = {}
    event = _make_event()
    outbox[event.id] = event
    publisher = FakeEventPublisher(error=RuntimeError("broker down"))

    process = ProcessOutboxEvents(
        uow_factory=lambda: InMemoryUnitOfWork(outbox=outbox),
        publisher=publisher,
        topic=TOPIC,
        max_retries=3,
    )

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
