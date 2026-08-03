"""Kafka background loops: outbox publisher + shipment consumer."""

from __future__ import annotations

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from application.services.order_notifications import OrderNotifier
from application.usecases.process_outbox_events import ProcessOutboxEvents
from application.usecases.process_shipment_event import (
    ProcessShipmentEvent,
    parse_shipment_payload,
)
from infrastructure.http.notifications import HttpNotificationsClient
from infrastructure.messaging.kafka_publisher import AIOKafkaEventPublisher
from infrastructure.persistence.uow import SQLAlchemyUnitOfWork
from settings import Settings

logger = logging.getLogger(__name__)


async def outbox_worker_loop(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    stop: asyncio.Event,
) -> None:
    publisher = AIOKafkaEventPublisher(settings.kafka_bootstrap_servers)
    process = ProcessOutboxEvents(
        uow_factory=lambda: SQLAlchemyUnitOfWork(session_factory),
        publisher=publisher,
        topic=settings.kafka_order_events_topic,
        batch_size=settings.outbox_batch_size,
        max_retries=settings.outbox_max_retries,
    )

    while not stop.is_set():
        try:
            await publisher.start()
            break
        except Exception:
            logger.exception("Outbox worker: Kafka connect failed, retry in 5s")
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass
    if stop.is_set():
        return

    logger.info(
        "Outbox worker started topic=%s poll=%ss",
        settings.kafka_order_events_topic,
        settings.outbox_poll_interval_seconds,
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
        logger.info("Outbox worker stopped")


async def shipment_consumer_loop(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    stop: asyncio.Event,
) -> None:
    notifier = OrderNotifier(
        HttpNotificationsClient(
            base_url=settings.capashino_base_url,
            api_token=settings.api_token,
        ),
    )
    process = ProcessShipmentEvent(
        uow_factory=lambda: SQLAlchemyUnitOfWork(session_factory),
        notifier=notifier,
    )

    consumer: AIOKafkaConsumer | None = None
    while not stop.is_set():
        try:
            consumer = AIOKafkaConsumer(
                settings.kafka_shipment_events_topic,
                bootstrap_servers=settings.kafka_bootstrap_servers,
                group_id=settings.kafka_consumer_group_id,
                enable_auto_commit=False,
                auto_offset_reset="earliest",
            )
            await consumer.start()
            break
        except Exception:
            logger.exception("Shipment consumer: Kafka connect failed, retry in 5s")
            if consumer is not None:
                try:
                    await consumer.stop()
                except Exception:
                    pass
                consumer = None
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass

    if stop.is_set() or consumer is None:
        return

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
                    await _handle_shipment_message(process, consumer, message)
    finally:
        await consumer.stop()
        logger.info("Shipment consumer stopped")


async def _handle_shipment_message(
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
