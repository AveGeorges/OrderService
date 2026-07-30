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
├── app.py               # create_app() (фабрика FastAPI)
└── settings.py          # конфигурация
bin/
└── api.py               # точка запуска API
```

## Локальный запуск

```bash
uv sync --group dev
uv run python -m bin.api
```

Healthcheck: `GET /health`
