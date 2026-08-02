"""Shipment events consumer: Kafka → inbox → order status."""

from __future__ import annotations

import asyncio
import json
import logging
import signal

from aiokafka import AIOKafkaConsumer

from application.usecases.process_shipment_event import (
    ProcessShipmentEvent,
    parse_shipment_payload,
)
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
    process = ProcessShipmentEvent(
        uow_factory=lambda: SQLAlchemyUnitOfWork(session_factory),
    )

    consumer = AIOKafkaConsumer(
        settings.kafka_shipment_events_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
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
            signal.signal(sig, lambda *_: _request_stop())

    await consumer.start()
    logger.info(
        "Shipment consumer started topic=%s group=%s",
        settings.kafka_shipment_events_topic,
        settings.kafka_consumer_group_id,
    )

    try:
        while not stop.is_set():
            batch = await consumer.getmany(timeout_ms=1000, max_records=50)
            if not batch:
                continue

            for _tp, messages in batch.items():
                for message in messages:
                    if stop.is_set():
                        break
                    await _handle_message(process, consumer, message)
    finally:
        await consumer.stop()
        await engine.dispose()
        logger.info("Shipment consumer stopped")


async def _handle_message(
    process: ProcessShipmentEvent,
    consumer: AIOKafkaConsumer,
    message: object,
) -> None:
    try:
        raw = message.value  # type: ignore[attr-defined]
        if raw is None:
            logger.warning("Empty Kafka message, skipping")
            await consumer.commit()
            return

        payload = json.loads(raw.decode("utf-8"))
        command = parse_shipment_payload(payload)
        await process(command)
        await consumer.commit()
    except Exception:
        logger.exception(
            "Failed to process shipment message offset=%s",
            getattr(message, "offset", None),
        )
        await asyncio.sleep(1)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
