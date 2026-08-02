from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SendNotificationRequest:
    message: str
    reference_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class Notification:
    id: str
    user_id: str
    message: str
    reference_id: str


class NotificationsClient(ABC):
    @abstractmethod
    async def send(self, request: SendNotificationRequest) -> Notification:
        raise NotImplementedError
