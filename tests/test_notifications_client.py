import httpx
import pytest

from application.exceptions import NotificationsServiceError
from application.ports.notifications import SendNotificationRequest
from infrastructure.http.notifications import HttpNotificationsClient


@pytest.mark.asyncio
async def test_http_notifications_send_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "token"
        assert request.url.path.endswith("/api/notifications")
        body = request.read()
        assert b"user_id" in body
        assert b"idempotency_key" in body
        assert b"reference_id" in body
        return httpx.Response(
            200,
            json={
                "id": "notification-1",
                "user_id": "user-1",
                "message": "NEW: Ваш заказ создан и ожидает оплаты",
                "reference_id": "order-1",
                "created_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        notifications = HttpNotificationsClient(
            "https://capashino.test",
            "token",
            client=client,
        )
        result = await notifications.send(
            SendNotificationRequest(
                user_id="user-1",
                message="NEW: Ваш заказ создан и ожидает оплаты",
                reference_id="order-1",
                idempotency_key="order-1:NEW",
            ),
        )

    assert result.id == "notification-1"
    assert result.user_id == "user-1"
    assert result.reference_id == "order-1"
    assert "NEW" in result.message


@pytest.mark.asyncio
async def test_http_notifications_server_error() -> None:
    transport = httpx.MockTransport(lambda _r: httpx.Response(503, text="down"))
    async with httpx.AsyncClient(transport=transport) as client:
        notifications = HttpNotificationsClient(
            "https://capashino.test",
            "token",
            client=client,
        )
        with pytest.raises(NotificationsServiceError):
            await notifications.send(
                SendNotificationRequest(
                    user_id="user-1",
                    message="test",
                    reference_id="order-1",
                    idempotency_key="k",
                ),
            )
