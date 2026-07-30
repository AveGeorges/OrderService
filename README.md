# Order Service

Сервис заказов с интеграцией Capashino (Catalog, Payments, Shipping, Notifications).
Построен по принципам чистой архитектуры.

## Структура

```
src/
├── domain/              # сущности и доменные исключения
├── application/         # ports + usecases
├── infrastructure/      # БД, HTTP-клиенты, messaging
├── presentation/        # FastAPI роуты и схемы
├── app.py               # create_app()
└── settings.py          # конфигурация
bin/
└── api.py               # точка запуска API
```

## Локальный запуск

```bash
cp .env.example .env
# заполните API_TOKEN

uv sync --group dev
uv run python -m bin.api
```

Или через Docker Compose (API + Postgres):

```bash
docker compose up --build
```

Healthcheck: `GET /health`

## Переменные окружения

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | SQLAlchemy async URL (`postgresql+asyncpg://...`) |
| `DATABASE_AUTO_CREATE` | Создавать таблицы при старте (`true`/`false`) |
| `CAPASHINO_BASE_URL` | Базовый URL Capashino (в кластере — internal hostname) |
| `API_TOKEN` | Токен для заголовка `X-API-Key` |
| `ORDER_SERVICE_INTERNAL_URL` | Internal DNS сервиса для payment callback: `http://<service>.<namespace>.svc:<port>` |
| `KAFKA_BOOTSTRAP_SERVERS` | Брокер Kafka, например `kafka.kafka.svc.cluster.local:9092` |
| `HOST` / `PORT` | Хост и порт API |

В LMS Portal добавьте эти переменные на детальной странице сервиса.

Для callback из Payments внутри кластера **не** используйте внешний `*.python-labs.ru` — только Kubernetes DNS:

```text
http://<service-name>.<namespace>.svc:8000/api/orders/payment-callback
```

## Качество кода

```bash
uv run ruff check .
uv run ruff format .
uv run pytest -q
```

Опционально: `pre-commit install` (см. `.pre-commit-config.yaml`).

## CI / Deploy

При пуше в `main` workflow `.github/workflows/deploy.yml`:

1. `ruff check` + `ruff format --check`
2. `pytest`
3. Сборка и push образа в `ghcr.io`
4. Deploy request в LMS

Нужен секрет `LMS_API_KEY`.
