from decimal import Decimal
from uuid import uuid4

import pytest

from application.exceptions import CatalogServiceError
from application.ports.catalog import CatalogItem
from application.usecases.create_order import CreateOrder, CreateOrderCommand
from application.usecases.get_order import GetOrder
from domain.entities import OrderStatus
from domain.exceptions import (
    InsufficientStockError,
    ItemNotFoundError,
    OrderNotFoundError,
)
from tests.fakes import FakeCatalogClient, InMemoryUnitOfWork


@pytest.fixture
def storage() -> dict:
    return {}


@pytest.fixture
def uow_factory(storage: dict):
    def factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(storage)

    return factory


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
    use_case = CreateOrder(uow_factory=uow_factory, catalog_client=catalog)

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
    assert order.item_id == "item-1"
    assert len(storage) == 1
    assert catalog.calls == ["item-1"]


@pytest.mark.asyncio
async def test_create_order_idempotent(uow_factory, storage: dict) -> None:
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
    use_case = CreateOrder(uow_factory=uow_factory, catalog_client=catalog)
    command = CreateOrderCommand(
        user_id="user-1",
        item_id="item-1",
        quantity=2,
        idempotency_key="same-key",
    )

    first = await use_case(command)
    second = await use_case(command)

    assert first.id == second.id
    assert len(storage) == 1
    assert catalog.calls == ["item-1"]


@pytest.mark.asyncio
async def test_create_order_insufficient_stock(uow_factory) -> None:
    catalog = FakeCatalogClient(
        {
            "item-1": CatalogItem(
                id="item-1",
                name="Product",
                price=Decimal("100.00"),
                available_qty=1,
            ),
        },
    )
    use_case = CreateOrder(uow_factory=uow_factory, catalog_client=catalog)

    with pytest.raises(InsufficientStockError):
        await use_case(
            CreateOrderCommand(
                user_id="user-1",
                item_id="item-1",
                quantity=5,
                idempotency_key="key-2",
            ),
        )


@pytest.mark.asyncio
async def test_create_order_item_not_found(uow_factory) -> None:
    catalog = FakeCatalogClient(missing_ids={"missing"})
    use_case = CreateOrder(uow_factory=uow_factory, catalog_client=catalog)

    with pytest.raises(ItemNotFoundError):
        await use_case(
            CreateOrderCommand(
                user_id="user-1",
                item_id="missing",
                quantity=1,
                idempotency_key="key-3",
            ),
        )


@pytest.mark.asyncio
async def test_create_order_catalog_unavailable(uow_factory) -> None:
    catalog = FakeCatalogClient(error=CatalogServiceError())
    use_case = CreateOrder(uow_factory=uow_factory, catalog_client=catalog)

    with pytest.raises(CatalogServiceError):
        await use_case(
            CreateOrderCommand(
                user_id="user-1",
                item_id="item-1",
                quantity=1,
                idempotency_key="key-4",
            ),
        )


@pytest.mark.asyncio
async def test_get_order_success(uow_factory, storage: dict) -> None:
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
    created = await CreateOrder(uow_factory=uow_factory, catalog_client=catalog)(
        CreateOrderCommand(
            user_id="user-1",
            item_id="item-1",
            quantity=1,
            idempotency_key="key-5",
        ),
    )

    order = await GetOrder(uow_factory=uow_factory)(created.id)
    assert order.id == created.id


@pytest.mark.asyncio
async def test_get_order_not_found(uow_factory) -> None:
    with pytest.raises(OrderNotFoundError):
        await GetOrder(uow_factory=uow_factory)(uuid4())
