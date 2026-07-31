from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app import create_app
from application.ports.catalog import CatalogItem
from application.usecases.create_order import CreateOrder
from application.usecases.get_order import GetOrder
from presentation.api.dependencies import (
    get_create_order_use_case,
    get_get_order_use_case,
)
from settings import Settings
from tests.fakes import FakeCatalogClient, InMemoryUnitOfWork


def _build_client() -> tuple[TestClient, dict, FakeCatalogClient]:
    storage: dict[UUID, object] = {}
    catalog = FakeCatalogClient(
        {
            "item-1": CatalogItem(
                id="item-1",
                name="Product",
                price=Decimal("100.00"),
                available_qty=10,
            ),
            "item-low": CatalogItem(
                id="item-low",
                name="Rare",
                price=Decimal("50.00"),
                available_qty=1,
            ),
        },
        missing_ids={"missing-item"},
    )

    def uow_factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(storage)  # type: ignore[arg-type]

    app = create_app(Settings(database_auto_create=False, api_token="test-token"))
    app.dependency_overrides[get_create_order_use_case] = lambda: CreateOrder(
        uow_factory=uow_factory,
        catalog_client=catalog,
    )
    app.dependency_overrides[get_get_order_use_case] = lambda: GetOrder(
        uow_factory=uow_factory,
    )
    return TestClient(app), storage, catalog  # type: ignore[return-value]


def test_create_order_api_201() -> None:
    with _build_client()[0] as client:
        response = client.post(
            "/api/orders",
            json={
                "user_id": "user-123",
                "quantity": 2,
                "item_id": "item-1",
                "idempotency_key": "idem-1",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == "user-123"
    assert body["quantity"] == 2
    assert body["item_id"] == "item-1"
    assert body["status"] == "NEW"
    assert "id" in body
    assert "created_at" in body
    assert "update_at" in body


def test_create_order_insufficient_stock_400() -> None:
    with _build_client()[0] as client:
        response = client.post(
            "/api/orders",
            json={
                "user_id": "user-123",
                "quantity": 5,
                "item_id": "item-low",
                "idempotency_key": "idem-2",
            },
        )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_create_order_item_not_found_400() -> None:
    with _build_client()[0] as client:
        response = client.post(
            "/api/orders",
            json={
                "user_id": "user-123",
                "quantity": 1,
                "item_id": "missing-item",
                "idempotency_key": "idem-3",
            },
        )

    assert response.status_code == 400


def test_create_order_idempotent() -> None:
    with _build_client()[0] as client:
        payload = {
            "user_id": "user-123",
            "quantity": 1,
            "item_id": "item-1",
            "idempotency_key": "same-idem",
        }
        first = client.post("/api/orders", json=payload)
        second = client.post("/api/orders", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_get_order_200() -> None:
    with _build_client()[0] as client:
        created = client.post(
            "/api/orders",
            json={
                "user_id": "user-123",
                "quantity": 1,
                "item_id": "item-1",
                "idempotency_key": "idem-get",
            },
        ).json()
        response = client.get(f"/api/orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_order_404() -> None:
    with _build_client()[0] as client:
        response = client.get(f"/api/orders/{uuid4()}")

    assert response.status_code == 404


def test_create_order_validation_error() -> None:
    with _build_client()[0] as client:
        response = client.post(
            "/api/orders",
            json={
                "user_id": "user-123",
                "quantity": 0,
                "item_id": "item-1",
                "idempotency_key": "idem-bad",
            },
        )

    assert response.status_code == 422
