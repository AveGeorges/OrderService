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
| `POSTGRES_HOST` | Хост Postgres (`localhost` локально, в compose — `db`, в LMS — из Portal) |
| `POSTGRES_PORT` | Порт Postgres |
| `POSTGRES_USERNAME` | Пользователь БД |
| `POSTGRES_PASSWORD` | Пароль БД |
| `POSTGRES_DATABASE_NAME` | Имя БД |
| `POSTGRES_CONNECTION_STRING` | Опционально: полный URL (`postgres://...`), будет приведён к `postgresql+asyncpg://` |
| `DATABASE_AUTO_CREATE` | Создавать таблицы при старте (`true`/`false`) |
| `CAPASHINO_BASE_URL` | Базовый URL Capashino (в кластере — internal hostname) |
| `API_TOKEN` | Токен для заголовка `X-API-Key` |
| `ORDER_SERVICE_INTERNAL_URL` | Internal DNS сервиса для payment callback |
| `KAFKA_BOOTSTRAP_SERVERS` | Брокер Kafka |
| `HOST` / `PORT` | Хост и порт API |

В LMS Portal переменные `POSTGRES_*` уже выдаются — код собирает из них async URL. Дополнительно `DATABASE_URL` задавать не нужно.

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
