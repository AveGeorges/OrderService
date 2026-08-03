import asyncio
import logging
from collections.abc import Callable

from application.ports.messaging import EventPublisher
from application.ports.notifications import (
    NotificationsClient,
    SendNotificationRequest,
)
from application.ports.uow import UnitOfWork
from application.services.order_notifications import is_notification_outbox_event
from domain.entities import OutboxEvent

logger = logging.getLogger(__name__)


class ProcessOutboxEvents:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        publisher: EventPublisher,
        notifications: NotificationsClient,
        *,
        topic: str,
        batch_size: int = 100,
        max_retries: int = 5,
        notify_attempts: int = 3,
        notify_retry_delay_seconds: float = 0.5,
    ) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._notifications = notifications
        self._topic = topic
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._notify_attempts = notify_attempts
        self._notify_retry_delay_seconds = notify_retry_delay_seconds

    async def __call__(self) -> int:
        async with self._uow_factory() as uow:
            events = await uow.outbox.get_pending_for_update(self._batch_size)
            if not events:
                return 0

            sent = 0
            for event in events:
                try:
                    if is_notification_outbox_event(event.event_type):
                        await self._publish_notification(event)
                    else:
                        await self._publish_kafka(event)
                    await uow.outbox.mark_as_sent(event.id)
                    sent += 1
                except Exception as exc:
                    logger.exception(
                        "Failed to process outbox event_id=%s type=%s",
                        event.id,
                        event.event_type,
                    )
                    await uow.outbox.mark_as_failed(
                        event.id,
                        str(exc),
                        max_retries=self._max_retries,
                    )

            await uow.commit()
            logger.info(
                "Outbox batch done total=%s sent=%s",
                len(events),
                sent,
            )
            return len(events)

    async def _publish_kafka(self, event: OutboxEvent) -> None:
        key = str(event.payload.get("order_id") or event.id)
        await self._publisher.publish(
            self._topic,
            key=key,
            payload=event.payload,
        )

    async def _publish_notification(self, event: OutboxEvent) -> None:
        request = SendNotificationRequest(
            user_id=str(event.payload["user_id"]),
            message=str(event.payload["message"]),
            reference_id=str(event.payload["reference_id"]),
            idempotency_key=str(event.payload["idempotency_key"]),
        )
        last_error: Exception | None = None
        for attempt in range(1, self._notify_attempts + 1):
            try:
                await self._notifications.send(request)
                logger.info(
                    "Notification published attempt=%s key=%s",
                    attempt,
                    request.idempotency_key,
                )
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Notification send failed attempt=%s/%s key=%s err=%s",
                    attempt,
                    self._notify_attempts,
                    request.idempotency_key,
                    exc,
                )
                if attempt < self._notify_attempts:
                    await asyncio.sleep(self._notify_retry_delay_seconds * attempt)
        assert last_error is not None
        raise last_error
