import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from application.ports.uow import UnitOfWork
from domain.entities import Order, OrderStatus
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
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, command: PaymentCallbackCommand) -> Order:
        async with self._uow_factory() as uow:
            order = await uow.orders.get_by_id(command.order_id)
            if order is None:
                raise OrderNotFoundError(str(command.order_id))

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
            else:
                logger.warning(
                    "Unknown payment status=%s order_id=%s",
                    command.status,
                    order.id,
                )
                return order

            updated = await uow.orders.update(order)
            await uow.commit()
            logger.info(
                "Payment callback applied order_id=%s status=%s payment_id=%s",
                updated.id,
                updated.status,
                command.payment_id,
            )
            return updated
