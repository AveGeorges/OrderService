import logging
from decimal import Decimal

import httpx

from application.exceptions import PaymentsServiceError
from application.ports.payments import CreatePaymentRequest, Payment, PaymentsClient

logger = logging.getLogger(__name__)


class HttpPaymentsClient(PaymentsClient):
    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._client = client
        self._timeout = timeout

    async def create_payment(self, request: CreatePaymentRequest) -> Payment:
        url = f"{self._base_url}/api/payments"
        headers = {"X-API-Key": self._api_token}
        payload = {
            "order_id": str(request.order_id),
            "amount": f"{request.amount:.2f}",
            "callback_url": request.callback_url,
            "idempotency_key": request.idempotency_key,
        }

        try:
            if self._client is not None:
                response = await self._client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            logger.exception(
                "Payments request failed for order_id=%s",
                request.order_id,
            )
            raise PaymentsServiceError("Payments service unavailable") from exc

        if response.status_code >= 400:
            logger.error(
                "Payments error status=%s order_id=%s body=%s",
                response.status_code,
                request.order_id,
                response.text,
            )
            raise PaymentsServiceError(
                f"Payments service returned status {response.status_code}",
            )

        data = response.json()
        return Payment(
            id=str(data["id"]),
            user_id=str(data["user_id"]),
            order_id=str(data["order_id"]),
            amount=Decimal(str(data["amount"])),
            status=str(data["status"]),
            idempotency_key=str(data["idempotency_key"]),
            created_at=str(data["created_at"]),
        )
