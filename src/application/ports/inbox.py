from abc import ABC, abstractmethod

from domain.entities import InboxEvent


class InboxRepository(ABC):
    @abstractmethod
    async def add(self, event: InboxEvent) -> InboxEvent | None:
        """Insert inbox event. Returns None if event_id already exists."""
        raise NotImplementedError

    @abstractmethod
    async def exists(self, event_id: str) -> bool:
        raise NotImplementedError
