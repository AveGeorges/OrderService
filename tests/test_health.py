from fastapi.testclient import TestClient

from app import create_app
from settings import Settings


def test_health() -> None:
    app = create_app(
        Settings(
            database_auto_create=False,
            run_kafka_workers_in_api=False,
        ),
    )
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
