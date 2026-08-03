import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from application.ports.uow import UnitOfWork
from application.services.order_notifications import OrderNotifier
from domain.entities import EventType, Order, OrderStatus, OutboxEvent
from domain.exceptions import OrderNotFoundError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PaymentCallbackCommand:
    payment_id: str
    order_id: UUID
    status: str
    amount: str
    error_message: str | None = None


class ProcessPaymentCallback:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        notifier: OrderNotifier,
    ) -> None:
        self._uow_factory = uow_factory
        self._notifier = notifier

    async def __call__(self, command: PaymentCallbackCommand) -> Order:
        async with self._uow_factory() as uow:
            order = await uow.orders.get_by_id(command.order_id)
            if order is None:
                raise OrderNotFoundError(str(command.order_id))

            emit_order_paid = False
            notify_status: OrderStatus | None = None
            notify_reason: str | None = None
            normalized = command.status.lower()
            if normalized == "succeeded":
                if order.status == OrderStatus.PAID:
                    logger.info(
                        "Idempotent payment callback succeeded order_id=%s",
                        order.id,
                    )
                    return order
                if order.status in {OrderStatus.SHIPPED, OrderStatus.CANCELLED}:
                    logger.info(
                        "Ignore succeeded callback for terminal status=%s order_id=%s",
                        order.status,
                        order.id,
                    )
                    return order
                order.mark_paid()
                emit_order_paid = True
                notify_status = OrderStatus.PAID
            elif normalized == "failed":
                if order.status == OrderStatus.CANCELLED:
                    logger.info(
                        "Idempotent payment callback failed order_id=%s",
                        order.id,
                    )
                    return order
                if order.status in {OrderStatus.PAID, OrderStatus.SHIPPED}:
                    logger.info(
                        "Ignore failed callback for status=%s order_id=%s",
                        order.status,
                        order.id,
                    )
                    return order
                order.mark_cancelled()
                notify_status = OrderStatus.CANCELLED
                notify_reason = command.error_message or "ошибка оплаты"
            else:
                logger.warning(
                    "Unknown payment status=%s order_id=%s",
                    command.status,
                    order.id,
                )
                return order

            updated = await uow.orders.update(order)
            if emit_order_paid:
                await uow.outbox.add(_order_paid_outbox_event(updated))
            await uow.commit()
            logger.info(
                "Payment callback applied order_id=%s status=%s payment_id=%s",
                updated.id,
                updated.status,
                command.payment_id,
            )

        if notify_status is not None:
            await self._notifier.notify_status(
                updated.id,
                notify_status,
                user_id=updated.user_id,
                reason=notify_reason,
            )
        return updated


def _order_paid_outbox_event(order: Order) -> OutboxEvent:
    return OutboxEvent(
        event_type=EventType.ORDER_PAID,
        payload={
            "event_type": EventType.ORDER_PAID,
            "order_id": str(order.id),
            "item_id": order.item_id,
            "quantity": order.quantity,
            "idempotency_key": order.idempotency_key,
        },
    )
