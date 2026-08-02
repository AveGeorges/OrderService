"""Outbox worker: publish PENDING events to Kafka."""

from __future__ import annotations

import asyncio
import logging
import signal

from application.usecases.process_outbox_events import ProcessOutboxEvents
from infrastructure.messaging.kafka_publisher import AIOKafkaEventPublisher
from infrastructure.persistence.database import create_engine, create_session_factory
from infrastructure.persistence.uow import SQLAlchemyUnitOfWork
from settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    if not settings.kafka_bootstrap_servers:
        raise SystemExit("KAFKA_BOOTSTRAP_SERVERS is not set")

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    publisher = AIOKafkaEventPublisher(settings.kafka_bootstrap_servers)
    process = ProcessOutboxEvents(
        uow_factory=lambda: SQLAlchemyUnitOfWork(session_factory),
        publisher=publisher,
        topic=settings.kafka_order_events_topic,
        batch_size=settings.outbox_batch_size,
        max_retries=settings.outbox_max_retries,
    )

    stop = asyncio.Event()

    def _request_stop() -> None:
        logger.info("Shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows: signal handlers in asyncio are limited
            signal.signal(sig, lambda *_: _request_stop())

    await publisher.start()
    logger.info(
        "Outbox worker started topic=%s poll=%ss batch=%s",
        settings.kafka_order_events_topic,
        settings.outbox_poll_interval_seconds,
        settings.outbox_batch_size,
    )

    try:
        while not stop.is_set():
            try:
                processed = await process()
            except Exception:
                logger.exception("Outbox poll failed")
                processed = 0

            if processed == 0:
                try:
                    await asyncio.wait_for(
                        stop.wait(),
                        timeout=settings.outbox_poll_interval_seconds,
                    )
                except TimeoutError:
                    pass
    finally:
        await publisher.stop()
        await engine.dispose()
        logger.info("Outbox worker stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
