"""Shipment events consumer: Kafka → inbox → order status."""

from __future__ import annotations

import asyncio
import logging
import signal

from infrastructure.messaging.workers import shipment_consumer_loop
from infrastructure.persistence.database import create_engine, create_session_factory
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

    try:
        await shipment_consumer_loop(session_factory, settings, stop)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
