from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.inbox import InboxRepository
from application.ports.outbox import OutboxRepository
from application.ports.repositories import OrderRepository
from domain.entities import (
    InboxEvent,
    Order,
    OrderStatus,
    OutboxEvent,
    OutboxStatus,
)
from infrastructure.persistence.models import InboxModel, OrderModel, OutboxModel


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


class SQLAlchemyOutboxRepository(OutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: OutboxEvent) -> OutboxEvent:
        model = OutboxModel(
            id=event.id,
            event_type=event.event_type,
            payload=event.payload,
            status=event.status.value,
            retry_count=event.retry_count,
            last_error=event.last_error,
            created_at=event.created_at,
            sent_at=event.sent_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def get_pending_for_update(self, limit: int = 100) -> list[OutboxEvent]:
        stmt = (
            select(OutboxModel)
            .where(OutboxModel.status == OutboxStatus.PENDING.value)
            .order_by(OutboxModel.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars().all()]

    async def mark_as_sent(self, event_id: UUID) -> None:
        model = await self._session.get(OutboxModel, event_id)
        if model is None:
            raise ValueError(f"Outbox event not found: {event_id}")
        model.status = OutboxStatus.SENT.value
        model.sent_at = datetime.now(UTC)
        await self._session.flush()

    async def mark_as_failed(
        self,
        event_id: UUID,
        error: str,
        *,
        max_retries: int = 5,
    ) -> None:
        model = await self._session.get(OutboxModel, event_id)
        if model is None:
            raise ValueError(f"Outbox event not found: {event_id}")
        model.retry_count += 1
        model.last_error = error[:2000]
        if model.retry_count >= max_retries:
            model.status = OutboxStatus.FAILED.value
        await self._session.flush()

    @staticmethod
    def _to_entity(model: OutboxModel) -> OutboxEvent:
        return OutboxEvent(
            id=model.id,
            event_type=model.event_type,
            payload=dict(model.payload),
            status=OutboxStatus(model.status),
            retry_count=model.retry_count,
            last_error=model.last_error,
            created_at=model.created_at,
            sent_at=model.sent_at,
        )


class SQLAlchemyInboxRepository(InboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: InboxEvent) -> InboxEvent | None:
        stmt = (
            pg_insert(InboxModel)
            .values(
                id=event.id,
                event_id=event.event_id,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
                processed_at=event.processed_at or datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
            .returning(InboxModel)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        await self._session.flush()
        return self._to_entity(model)

    async def exists(self, event_id: str) -> bool:
        stmt = select(InboxModel.id).where(InboxModel.event_id == event_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _to_entity(model: InboxModel) -> InboxEvent:
        return InboxEvent(
            id=model.id,
            event_id=model.event_id,
            event_type=model.event_type,
            payload=dict(model.payload),
            created_at=model.created_at,
            processed_at=model.processed_at,
        )
