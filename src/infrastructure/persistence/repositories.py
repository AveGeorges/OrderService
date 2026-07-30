"""Order repository implementation — completed in stage 1."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.repositories import OrderRepository
from domain.entities import Order, OrderStatus
from infrastructure.persistence.models import OrderModel


class SQLAlchemyOrderRepository(OrderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, order: Order) -> Order:
        model = OrderModel(
            id=order.id,
            user_id=order.user_id,
            item_id=order.item_id,
            quantity=order.quantity,
            status=order.status.value,
            idempotency_key=order.idempotency_key,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def get_by_id(self, order_id: UUID) -> Order | None:
        model = await self._session.get(OrderModel, order_id)
        return self._to_entity(model) if model else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        stmt = select(OrderModel).where(OrderModel.idempotency_key == idempotency_key)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def update(self, order: Order) -> Order:
        model = await self._session.get(OrderModel, order.id)
        if model is None:
            raise ValueError(f"Order not found: {order.id}")
        model.user_id = order.user_id
        model.item_id = order.item_id
        model.quantity = order.quantity
        model.status = order.status.value
        model.idempotency_key = order.idempotency_key
        model.updated_at = order.updated_at
        await self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: OrderModel) -> Order:
        return Order(
            id=model.id,
            user_id=model.user_id,
            item_id=model.item_id,
            quantity=model.quantity,
            status=OrderStatus(model.status),
            idempotency_key=model.idempotency_key,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
