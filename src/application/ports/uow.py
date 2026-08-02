from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from application.ports.inbox import InboxRepository
from application.ports.outbox import OutboxRepository
from application.ports.repositories import OrderRepository


class UnitOfWork(ABC):
    orders: OrderRepository
    outbox: OutboxRepository
    inbox: InboxRepository

    @abstractmethod
    async def __aenter__(self) -> Self:
        raise NotImplementedError

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError
