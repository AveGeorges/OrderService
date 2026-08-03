from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from application.exceptions import PaymentsServiceError
from application.ports.payments import CreatePaymentRequest
from infrastructure.http.payments import HttpPaymentsClient


@pytest.mark.asyncio
async def test_http_payments_create_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "token"
        assert request.url.path.endswith("/api/payments")
        body = request.read()
        assert b"callback_url" in body
        return httpx.Response(
            200,
            json={
                "id": "payment-1",
                "user_id": "user-1",
                "order_id": "order-1",
                "amount": "200.00",
                "status": "pending",
                "idempotency_key": "key-1",
                "created_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        payments = HttpPaymentsClient(
            "https://capashino.test",
            "token",
            client=client,
        )
        payment = await payments.create_payment(
            CreatePaymentRequest(
                order_id=uuid4(),
                amount=Decimal("200.00"),
                callback_url="http://svc/api/orders/payment-callback",
                idempotency_key="key-1",
            ),
        )

    assert payment.id == "payment-1"
    assert payment.user_id == "user-1"
    assert payment.status == "pending"
    assert payment.created_at == "2024-01-01T00:00:00Z"


@pytest.mark.asyncio
async def test_http_payments_server_error() -> None:
    transport = httpx.MockTransport(lambda _r: httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(transport=transport) as client:
        payments = HttpPaymentsClient(
            "https://capashino.test",
            "token",
            client=client,
        )
        with pytest.raises(PaymentsServiceError):
            await payments.create_payment(
                CreatePaymentRequest(
                    order_id=uuid4(),
                    amount=Decimal("10.00"),
                    callback_url="http://svc/callback",
                    idempotency_key="k",
                ),
            )
