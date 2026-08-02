from abc import ABC, abstractmethod
from uuid import UUID

from domain.entities import OutboxEvent


class OutboxRepository(ABC):
    @abstractmethod
    async def add(self, event: OutboxEvent) -> OutboxEvent:
        raise NotImplementedError

    @abstractmethod
    async def get_pending_for_update(self, limit: int = 100) -> list[OutboxEvent]:
        """Fetch pending events with row locks (FOR UPDATE SKIP LOCKED)."""
        raise NotImplementedError

    @abstractmethod
    async def mark_as_sent(self, event_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def mark_as_failed(
        self,
        event_id: UUID,
        error: str,
        *,
        max_retries: int = 5,
    ) -> None:
        """Increment retry_count; set FAILED when retry_count >= max_retries."""
        raise NotImplementedError
