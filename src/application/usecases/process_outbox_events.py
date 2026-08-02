import logging
from collections.abc import Callable

from application.ports.messaging import EventPublisher
from application.ports.uow import UnitOfWork

logger = logging.getLogger(__name__)


class ProcessOutboxEvents:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        publisher: EventPublisher,
        *,
        topic: str,
        batch_size: int = 100,
        max_retries: int = 5,
    ) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._topic = topic
        self._batch_size = batch_size
        self._max_retries = max_retries

    async def __call__(self) -> int:
        async with self._uow_factory() as uow:
            events = await uow.outbox.get_pending_for_update(self._batch_size)
            if not events:
                return 0

            sent = 0
            for event in events:
                key = str(event.payload.get("order_id") or event.id)
                try:
                    await self._publisher.publish(
                        self._topic,
                        key=key,
                        payload=event.payload,
                    )
                    await uow.outbox.mark_as_sent(event.id)
                    sent += 1
                except Exception as exc:
                    logger.exception(
                        "Failed to publish outbox event_id=%s type=%s",
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
                "Outbox batch done total=%s sent=%s topic=%s",
                len(events),
                sent,
                self._topic,
            )
            return len(events)
