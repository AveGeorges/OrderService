import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer

from application.ports.messaging import EventPublisher

logger = logging.getLogger(__name__)


class AIOKafkaEventPublisher(EventPublisher):
    def __init__(self, bootstrap_servers: str) -> None:
        if not bootstrap_servers:
            raise ValueError("KAFKA_BOOTSTRAP_SERVERS is required")
        self._bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        if self._producer is not None:
            return
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            acks="all",
            enable_idempotence=True,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            key_serializer=lambda key: key.encode("utf-8") if key else None,
        )
        await self._producer.start()
        logger.info(
            "Kafka producer started bootstrap=%s",
            self._bootstrap_servers,
        )

    async def stop(self) -> None:
        if self._producer is None:
            return
        await self._producer.stop()
        self._producer = None
        logger.info("Kafka producer stopped")

    async def publish(
        self,
        topic: str,
        *,
        key: str,
        payload: dict[str, Any],
    ) -> None:
        if self._producer is None:
            raise RuntimeError("Kafka producer is not started")
        await self._producer.send_and_wait(topic, value=payload, key=key)
        logger.debug("Published topic=%s key=%s", topic, key)
