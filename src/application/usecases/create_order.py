import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from application.ports.catalog import CatalogClient
from application.ports.uow import UnitOfWork
from domain.entities import Order, OrderStatus
from domain.exceptions import InsufficientStockError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateOrderCommand:
    user_id: str
    item_id: str
    quantity: int
    idempotency_key: str


class CreateOrder:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        catalog_client: CatalogClient,
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog_client

    async def __call__(self, command: CreateOrderCommand) -> Order:
        async with self._uow_factory() as uow:
            existing = await uow.orders.get_by_idempotency_key(command.idempotency_key)
            if existing is not None:
                logger.info(
                    "Idempotent create_order hit key=%s order_id=%s",
                    command.idempotency_key,
                    existing.id,
                )
                return existing

        item = await self._catalog.get_item(command.item_id)
        if item.available_qty < command.quantity:
            raise InsufficientStockError(
                item_id=command.item_id,
                requested=command.quantity,
                available=item.available_qty,
            )

        order = Order(
            id=uuid4(),
            user_id=command.user_id,
            item_id=command.item_id,
            quantity=command.quantity,
            status=OrderStatus.NEW,
            idempotency_key=command.idempotency_key,
        )

        async with self._uow_factory() as uow:
            existing = await uow.orders.get_by_idempotency_key(command.idempotency_key)
            if existing is not None:
                return existing

            saved = await uow.orders.add(order)
            await uow.commit()
            logger.info("Order created id=%s status=%s", saved.id, saved.status)
            return saved
