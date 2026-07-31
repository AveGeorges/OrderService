from collections.abc import Callable
from uuid import UUID

from application.ports.uow import UnitOfWork
from domain.entities import Order
from domain.exceptions import OrderNotFoundError


class GetOrder:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, order_id: UUID) -> Order:
        async with self._uow_factory() as uow:
            order = await uow.orders.get_by_id(order_id)
            if order is None:
                raise OrderNotFoundError(str(order_id))
            return order
