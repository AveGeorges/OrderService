from decimal import Decimal
from uuid import uuid4

import pytest

from application.exceptions import CatalogServiceError, PaymentsServiceError
from application.ports.catalog import CatalogItem
from application.services.order_notifications import is_notification_outbox_event
from application.usecases.create_order import CreateOrder, CreateOrderCommand
from application.usecases.get_order import GetOrder
from application.usecases.process_payment_callback import (
    PaymentCallbackCommand,
    ProcessPaymentCallback,
)
from domain.entities import EventType, OrderStatus, OutboxStatus
from domain.exceptions import (
    InsufficientStockError,
    ItemNotFoundError,
    OrderNotFoundError,
)
from tests.fakes import (
    FakeCatalogClient,
    FakePaymentsClient,
    InMemoryUnitOfWork,
)

CALLBACK_URL = "http://order-service.svc:8000/api/orders/payment-callback"


@pytest.fixture
def storage() -> dict:
    return {}


@pytest.fixture
def outbox_storage() -> dict:
    return {}


@pytest.fixture
def uow_factory(storage: dict, outbox_storage: dict):
    def factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(storage, outbox_storage)

    return factory


def _create_order(
    uow_factory,
    catalog: FakeCatalogClient,
    payments: FakePaymentsClient | None = None,
) -> CreateOrder:
    return CreateOrder(
        uow_factory=uow_factory,
        catalog_client=catalog,
        payments_client=payments or FakePaymentsClient(),
        payment_callback_url=CALLBACK_URL,
    )


def _order_paid_events(outbox: dict) -> list:
    return [e for e in outbox.values() if e.event_type == EventType.ORDER_PAID]


@pytest.mark.asyncio
async def test_create_order_success(uow_factory, storage: dict) -> None:
    catalog = FakeCatalogClient(
        {
            "item-1": CatalogItem(
                id="item-1",
                name="Product",
                price=Decimal("100.00"),
                available_qty=10,
            ),
        },
    )
    payments = FakePaymentsClient()
    use_case = _create_order(uow_factory, catalog, payments)

    order = await use_case(
        CreateOrderCommand(
            user_id="user-1",
            item_id="item-1",
            quantity=2,
            idempotency_key="key-1",
        ),
    )

    assert order.status == OrderStatus.NEW
    assert order.quantity == 2
    assert len(storage) == 1
    assert len(payments.calls) == 1
    assert payments.calls[0].amount == Decimal("200.00")
    assert payments.calls[0].callback_url == CALLBACK_URL


@pytest.mark.asyncio
async def test_create_order_idempotent(uow_factory, storage: dict) -> None:
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
    use_case = _create_order(uow_factory, catalog)
    command = CreateOrderCommand(
        user_id="user-1",
        item_id="item-1",
        quantity=1,
        idempotency_key="same-key",
    )
    first = await use_case(command)
    second = await use_case(command)
    assert first.id == second.id
    assert len(storage) == 1


@pytest.mark.asyncio
async def test_create_order_insufficient_stock(uow_factory) -> None:
    catalog = FakeCatalogClient(
        {
            "item-1": CatalogItem(
                id="item-1",
                name="Product",
                price=Decimal("10.00"),
                available_qty=1,
            ),
        },
    )
    with pytest.raises(InsufficientStockError):
        await _create_order(uow_factory, catalog)(
            CreateOrderCommand(
                user_id="user-1",
                item_id="item-1",
                quantity=5,
                idempotency_key="k",
            ),
        )


@pytest.mark.asyncio
async def test_create_order_item_not_found(uow_factory) -> None:
    catalog = FakeCatalogClient(missing_ids={"missing"})
    with pytest.raises(ItemNotFoundError):
        await _create_order(uow_factory, catalog)(
            CreateOrderCommand(
                user_id="user-1",
                item_id="missing",
                quantity=1,
                idempotency_key="k",
            ),
        )


@pytest.mark.asyncio
async def test_create_order_catalog_error(uow_factory) -> None:
    catalog = FakeCatalogClient(error=CatalogServiceError("down"))
    with pytest.raises(CatalogServiceError):
        await _create_order(uow_factory, catalog)(
            CreateOrderCommand(
                user_id="user-1",
                item_id="item-1",
                quantity=1,
                idempotency_key="k",
            ),
        )


@pytest.mark.asyncio
async def test_create_order_payment_error_cancels(
    uow_factory,
    storage: dict,
    outbox_storage: dict,
) -> None:
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
    payments = FakePaymentsClient(error=PaymentsServiceError("pay fail"))
    with pytest.raises(PaymentsServiceError):
        await _create_order(uow_factory, catalog, payments)(
            CreateOrderCommand(
                user_id="user-1",
                item_id="item-1",
                quantity=1,
                idempotency_key="pay-fail",
            ),
        )
    order = next(iter(storage.values()))
    assert order.status == OrderStatus.CANCELLED
    keys = [
        e.payload["idempotency_key"]
        for e in outbox_storage.values()
        if is_notification_outbox_event(e.event_type)
    ]
    assert any(k.endswith(":NEW") for k in keys)
    assert any(k.endswith(":CANCELLED") for k in keys)


@pytest.mark.asyncio
async def test_get_order(uow_factory, storage: dict) -> None:
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
    created = await _create_order(uow_factory, catalog)(
        CreateOrderCommand(
            user_id="user-1",
            item_id="item-1",
            quantity=1,
            idempotency_key="get-1",
        ),
    )
    got = await GetOrder(uow_factory=uow_factory)(created.id)
    assert got.id == created.id


@pytest.mark.asyncio
async def test_get_order_not_found(uow_factory) -> None:
    with pytest.raises(OrderNotFoundError):
        await GetOrder(uow_factory=uow_factory)(uuid4())


@pytest.mark.asyncio
async def test_payment_callback_succeeded(
    uow_factory,
    outbox_storage: dict,
) -> None:
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
    order = await _create_order(uow_factory, catalog)(
        CreateOrderCommand(
            user_id="user-1",
            item_id="item-1",
            quantity=1,
            idempotency_key="cb-ok",
        ),
    )

    updated = await ProcessPaymentCallback(uow_factory)(
        PaymentCallbackCommand(
            payment_id="pay-1",
            order_id=order.id,
            status="succeeded",
            amount="10.00",
        ),
    )
    assert updated.status == OrderStatus.PAID
    paid_events = _order_paid_events(outbox_storage)
    assert len(paid_events) == 1
    event = paid_events[0]
    assert event.status == OutboxStatus.PENDING
    assert event.payload == {
        "event_type": EventType.ORDER_PAID,
        "order_id": str(order.id),
        "item_id": "item-1",
        "quantity": 1,
        "idempotency_key": "cb-ok",
    }

    again = await ProcessPaymentCallback(uow_factory)(
        PaymentCallbackCommand(
            payment_id="pay-1",
            order_id=order.id,
            status="succeeded",
            amount="10.00",
        ),
    )
    assert again.status == OrderStatus.PAID
    assert len(_order_paid_events(outbox_storage)) == 1


@pytest.mark.asyncio
async def test_payment_callback_failed(
    uow_factory,
    outbox_storage: dict,
) -> None:
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
    order = await _create_order(uow_factory, catalog)(
        CreateOrderCommand(
            user_id="user-1",
            item_id="item-1",
            quantity=1,
            idempotency_key="cb-fail",
        ),
    )

    updated = await ProcessPaymentCallback(uow_factory)(
        PaymentCallbackCommand(
            payment_id="pay-2",
            order_id=order.id,
            status="failed",
            amount="10.00",
            error_message="fail",
        ),
    )
    assert updated.status == OrderStatus.CANCELLED
    assert _order_paid_events(outbox_storage) == []
    assert any(
        e.payload.get("idempotency_key", "").endswith(":CANCELLED")
        for e in outbox_storage.values()
        if is_notification_outbox_event(e.event_type)
    )
