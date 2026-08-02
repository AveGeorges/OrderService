from datetime import UTC, datetime
from uuid import uuid4

import pytest

from application.services.order_notifications import OrderNotifier
from application.usecases.process_shipment_event import (
    ProcessShipmentEvent,
    ShipmentEventCommand,
    build_shipment_event_id,
    parse_shipment_payload,
)
from domain.entities import EventType, Order, OrderStatus
from domain.exceptions import OrderNotFoundError
from tests.fakes import FakeNotificationsClient, InMemoryUnitOfWork


def _notifier() -> OrderNotifier:
    return OrderNotifier(FakeNotificationsClient())


def _paid_order(**overrides: object) -> Order:
    data = {
        "id": uuid4(),
        "user_id": "user-1",
        "item_id": "item-1",
        "quantity": 2,
        "status": OrderStatus.PAID,
        "idempotency_key": "key-1",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    data.update(overrides)
    return Order(**data)  # type: ignore[arg-type]


async def test_order_shipped_updates_status_and_inbox() -> None:
    order = _paid_order()
    orders = {order.id: order}
    inbox: dict = {}
    notifications = FakeNotificationsClient()

    applied = await ProcessShipmentEvent(
        lambda: InMemoryUnitOfWork(orders, inbox=inbox),
        OrderNotifier(notifications),
    )(
        ShipmentEventCommand(
            event_id="ship-1",
            event_type=EventType.ORDER_SHIPPED,
            order_id=order.id,
            payload={
                "event_type": EventType.ORDER_SHIPPED,
                "order_id": str(order.id),
                "shipment_id": "shp-1",
            },
        ),
    )

    assert applied is True
    assert orders[order.id].status == OrderStatus.SHIPPED
    assert "ship-1" in inbox
    assert len(notifications.calls) == 1
    assert notifications.calls[0].idempotency_key == f"{order.id}:SHIPPED"


async def test_order_shipped_idempotent_via_inbox() -> None:
    order = _paid_order()
    orders = {order.id: order}
    inbox: dict = {}
    notifications = FakeNotificationsClient()
    process = ProcessShipmentEvent(
        lambda: InMemoryUnitOfWork(orders, inbox=inbox),
        OrderNotifier(notifications),
    )
    command = ShipmentEventCommand(
        event_id="ship-1",
        event_type=EventType.ORDER_SHIPPED,
        order_id=order.id,
        payload={
            "event_type": EventType.ORDER_SHIPPED,
            "order_id": str(order.id),
            "shipment_id": "shp-1",
        },
    )

    assert await process(command) is True
    assert await process(command) is False
    assert orders[order.id].status == OrderStatus.SHIPPED
    assert len(inbox) == 1
    assert len(notifications.calls) == 1


async def test_order_cancelled_by_shipping() -> None:
    order = _paid_order()
    orders = {order.id: order}
    inbox: dict = {}
    notifications = FakeNotificationsClient()

    applied = await ProcessShipmentEvent(
        lambda: InMemoryUnitOfWork(orders, inbox=inbox),
        OrderNotifier(notifications),
    )(
        ShipmentEventCommand(
            event_id="cancel-1",
            event_type=EventType.ORDER_CANCELLED,
            order_id=order.id,
            payload={
                "event_type": EventType.ORDER_CANCELLED,
                "order_id": str(order.id),
                "reason": "out of stock",
            },
        ),
    )

    assert applied is True
    assert orders[order.id].status == OrderStatus.CANCELLED
    assert "cancel-1" in inbox
    assert notifications.calls[0].message.endswith("out of stock")


async def test_order_cancelled_idempotent() -> None:
    order = _paid_order()
    orders = {order.id: order}
    inbox: dict = {}
    process = ProcessShipmentEvent(
        lambda: InMemoryUnitOfWork(orders, inbox=inbox),
        _notifier(),
    )
    command = ShipmentEventCommand(
        event_id="cancel-1",
        event_type=EventType.ORDER_CANCELLED,
        order_id=order.id,
        payload={
            "event_type": EventType.ORDER_CANCELLED,
            "order_id": str(order.id),
            "reason": "out of stock",
        },
    )

    assert await process(command) is True
    assert await process(command) is False
    assert len(inbox) == 1


async def test_shipment_order_not_found() -> None:
    missing_id = uuid4()
    with pytest.raises(OrderNotFoundError):
        await ProcessShipmentEvent(lambda: InMemoryUnitOfWork(), _notifier())(
            ShipmentEventCommand(
                event_id="ship-missing",
                event_type=EventType.ORDER_SHIPPED,
                order_id=missing_id,
                payload={
                    "event_type": EventType.ORDER_SHIPPED,
                    "order_id": str(missing_id),
                    "shipment_id": "shp-x",
                },
            ),
        )


def test_build_event_id_prefers_explicit() -> None:
    assert (
        build_shipment_event_id(
            {"event_id": "explicit-1", "event_type": "order.shipped"},
        )
        == "explicit-1"
    )


def test_parse_shipment_payload_builds_stable_id() -> None:
    order_id = uuid4()
    command = parse_shipment_payload(
        {
            "event_type": EventType.ORDER_SHIPPED,
            "order_id": str(order_id),
            "shipment_id": "shp-9",
        },
    )
    assert command.event_id == f"order.shipped:{order_id}:shp-9"
    assert command.order_id == order_id
