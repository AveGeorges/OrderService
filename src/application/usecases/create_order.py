import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from application.exceptions import PaymentsServiceError
from application.ports.catalog import CatalogClient
from application.ports.payments import CreatePaymentRequest, PaymentsClient
from application.ports.uow import UnitOfWork
from application.services.order_notifications import build_notification_outbox_for_order
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
        payments_client: PaymentsClient,
        payment_callback_url: str,
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog_client
        self._payments = payments_client
        self._payment_callback_url = payment_callback_url

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
            await uow.outbox.add(
                build_notification_outbox_for_order(saved, OrderStatus.NEW),
            )
            await uow.commit()
            logger.info("Order created id=%s status=%s", saved.id, saved.status)

        amount = (item.price * Decimal(command.quantity)).quantize(Decimal("0.01"))
        try:
            payment = await self._payments.create_payment(
                CreatePaymentRequest(
                    order_id=saved.id,
                    amount=amount,
                    callback_url=self._payment_callback_url,
                    idempotency_key=command.idempotency_key,
                ),
            )
            logger.info(
                "Payment created payment_id=%s order_id=%s status=%s",
                payment.id,
                saved.id,
                payment.status,
            )
        except PaymentsServiceError:
            logger.exception("Payment failed for order_id=%s, cancelling", saved.id)
            async with self._uow_factory() as uow:
                current = await uow.orders.get_by_id(saved.id)
                if current is not None and current.status == OrderStatus.NEW:
                    current.mark_cancelled()
                    saved = await uow.orders.update(current)
                    await uow.outbox.add(
                        build_notification_outbox_for_order(
                            saved,
                            OrderStatus.CANCELLED,
                            reason="ошибка оплаты",
                        ),
                    )
                    await uow.commit()
            raise

        return saved
