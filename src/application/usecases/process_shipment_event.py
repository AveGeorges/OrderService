import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from application.ports.uow import UnitOfWork
from application.services.order_notifications import OrderNotifier
from domain.entities import EventType, InboxEvent, Order, OrderStatus
from domain.exceptions import OrderNotFoundError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ShipmentEventCommand:
    event_id: str
    event_type: str
    order_id: UUID
    payload: dict[str, Any]


class ProcessShipmentEvent:
    """Apply Shipping events idempotently via inbox."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        notifier: OrderNotifier,
    ) -> None:
        self._uow_factory = uow_factory
        self._notifier = notifier

    async def __call__(self, command: ShipmentEventCommand) -> bool:
        """Return True if event was applied, False if duplicate (already in inbox)."""
        notify_status: OrderStatus | None = None
        notify_reason: str | None = None

        async with self._uow_factory() as uow:
            inserted = await uow.inbox.add(
                InboxEvent(
                    event_id=command.event_id,
                    event_type=command.event_type,
                    payload=command.payload,
                ),
            )
            if inserted is None:
                logger.info(
                    "Duplicate shipment event skipped event_id=%s order_id=%s",
                    command.event_id,
                    command.order_id,
                )
                return False

            order = await uow.orders.get_by_id(command.order_id)
            if order is None:
                raise OrderNotFoundError(str(command.order_id))

            changed = _apply_shipment_status(order, command)
            if changed:
                await uow.orders.update(order)
                notify_status = order.status
                if notify_status == OrderStatus.CANCELLED:
                    reason = command.payload.get("reason")
                    notify_reason = str(reason) if reason else None

            await uow.commit()
            logger.info(
                "Shipment event applied event_id=%s order_id=%s type=%s status=%s",
                command.event_id,
                order.id,
                command.event_type,
                order.status,
            )

        if notify_status is not None:
            await self._notifier.notify_status(
                command.order_id,
                notify_status,
                reason=notify_reason,
            )
        return True


def build_shipment_event_id(payload: dict[str, Any]) -> str:
    if payload.get("event_id"):
        return str(payload["event_id"])

    event_type = str(payload.get("event_type", "unknown"))
    order_id = str(payload.get("order_id", "unknown"))

    if event_type == EventType.ORDER_SHIPPED:
        suffix = str(payload.get("shipment_id") or "no-shipment")
    elif event_type == EventType.ORDER_CANCELLED:
        reason = str(payload.get("reason", ""))
        suffix = hashlib.sha256(reason.encode("utf-8")).hexdigest()[:16]
    else:
        suffix = "unknown"

    return f"{event_type}:{order_id}:{suffix}"


def parse_shipment_payload(payload: dict[str, Any]) -> ShipmentEventCommand:
    event_type = str(payload.get("event_type", ""))
    order_id_raw = payload.get("order_id")
    if not order_id_raw:
        raise ValueError("shipment event missing order_id")
    return ShipmentEventCommand(
        event_id=build_shipment_event_id(payload),
        event_type=event_type,
        order_id=UUID(str(order_id_raw)),
        payload=payload,
    )


def _apply_shipment_status(order: Order, command: ShipmentEventCommand) -> bool:
    if command.event_type == EventType.ORDER_SHIPPED:
        if order.status == OrderStatus.SHIPPED:
            return False
        if order.status == OrderStatus.CANCELLED:
            logger.info(
                "Ignore shipped for cancelled order_id=%s",
                order.id,
            )
            return False
        order.mark_shipped()
        return True

    if command.event_type == EventType.ORDER_CANCELLED:
        reason = command.payload.get("reason")
        if order.status == OrderStatus.CANCELLED:
            return False
        if order.status == OrderStatus.SHIPPED:
            logger.info(
                "Ignore cancelled for shipped order_id=%s reason=%s",
                order.id,
                reason,
            )
            return False
        order.mark_cancelled()
        logger.info(
            "Order cancelled by shipping order_id=%s reason=%s",
            order.id,
            reason,
        )
        return True

    logger.warning(
        "Unknown shipment event_type=%s event_id=%s",
        command.event_type,
        command.event_id,
    )
    return False
