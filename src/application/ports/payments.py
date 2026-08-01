from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CreatePaymentRequest:
    order_id: UUID
    amount: Decimal
    callback_url: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class Payment:
    id: str
    order_id: str
    amount: Decimal
    status: str
    idempotency_key: str


class PaymentsClient(ABC):
    @abstractmethod
    async def create_payment(self, request: CreatePaymentRequest) -> Payment:
        raise NotImplementedError
