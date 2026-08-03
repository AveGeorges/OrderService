import logging

import httpx

from application.exceptions import NotificationsServiceError
from application.ports.notifications import (
    Notification,
    NotificationsClient,
    SendNotificationRequest,
)

logger = logging.getLogger(__name__)


class HttpNotificationsClient(NotificationsClient):
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

    async def send(self, request: SendNotificationRequest) -> Notification:
        url = f"{self._base_url}/api/notifications"
        headers = {"X-API-Key": self._api_token}
        payload = {
            "user_id": request.user_id,
            "message": request.message,
            "reference_id": request.reference_id,
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
                "Notifications request failed reference_id=%s",
                request.reference_id,
            )
            raise NotificationsServiceError(
                "Notifications service unavailable",
            ) from exc

        if response.status_code >= 400:
            logger.error(
                "Notifications error status=%s reference_id=%s body=%s",
                response.status_code,
                request.reference_id,
                response.text,
            )
            raise NotificationsServiceError(
                f"Notifications service returned status {response.status_code}",
            )

        data = response.json()
        return Notification(
            id=str(data["id"]),
            user_id=str(data.get("user_id", "")),
            message=str(data["message"]),
            reference_id=str(data["reference_id"]),
        )
