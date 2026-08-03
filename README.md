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
├── api.py               # точка запуска API
├── outbox_worker.py     # публикация outbox → Kafka
└── shipment_consumer.py # Shipping events → inbox → статусы
```

## Локальный запуск

```bash
cp .env.example .env
# заполните API_TOKEN и при необходимости KAFKA_BOOTSTRAP_SERVERS

uv sync --group dev
uv run python -m bin.api
```

Kafka-воркеры (нужен брокер):

```bash
uv run python -m bin.outbox_worker
uv run python -m bin.shipment_consumer
```

Или через Docker Compose (API + Postgres):

```bash
docker compose up --build
```

С воркерами Kafka:

```bash
docker compose --profile kafka up --build
```

Роль контейнера задаётся `APP_ROLE`: `api` (по умолчанию), `outbox-worker`, `shipment-consumer`.

Healthcheck: `GET /health`

При `KAFKA_BOOTSTRAP_SERVERS` API сам поднимает outbox worker и shipment consumer

## Переменные окружения

| Переменная | Описание |
|---|---|
| `POSTGRES_HOST` | Хост Postgres (`localhost` локально, в compose — `db`, в LMS — из Portal) |
| `POSTGRES_PORT` | Порт Postgres |
| `POSTGRES_USERNAME` | Пользователь БД |
| `POSTGRES_PASSWORD` | Пароль БД |
| `POSTGRES_DATABASE_NAME` | Имя БД |
| `POSTGRES_CONNECTION_STRING` | Опционально: полный URL (`postgres://...`), будет приведён к `postgresql+asyncpg://` |
| `DATABASE_AUTO_CREATE` | Создавать таблицы при старте (`true`/`false`) |
| `CAPASHINO_BASE_URL` | Базовый URL Capashino (в кластере — internal hostname) |
| `API_TOKEN` | Токен для заголовка `X-API-Key` (Catalog / Payments / Notifications) |
| `ORDER_SERVICE_INTERNAL_URL` | Internal DNS сервиса для payment callback |
| `KAFKA_BOOTSTRAP_SERVERS` | Брокер Kafka (в LMS: `kafka.kafka.svc.cluster.local:9092`) |
| `RUN_KAFKA_WORKERS_IN_API` | Крутить outbox+consumer внутри API (`true` по умолчанию, для LMS) |
| `APP_ROLE` | Что запускает контейнер: `api` / `outbox-worker` / `shipment-consumer` |
| `KAFKA_ORDER_EVENTS_TOPIC` | Топик исходящих событий заказа (по умолчанию `student_system-order.events`) |
| `KAFKA_SHIPMENT_EVENTS_TOPIC` | Топик входящих событий доставки |
| `KAFKA_CONSUMER_GROUP_ID` | Consumer group для shipment events |
| `OUTBOX_POLL_INTERVAL_SECONDS` | Интервал опроса outbox воркером |
| `OUTBOX_BATCH_SIZE` | Размер батча outbox |
| `OUTBOX_MAX_RETRIES` | После скольких ошибок событие → `FAILED` |
| `HOST` / `PORT` | Хост и порт API |




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
