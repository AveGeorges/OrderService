#!/bin/sh
set -e

# В контейнере зависимости уже поставлены через uv sync.
# Локальный пакет не установлен editable — код доступен через PYTHONPATH.
export PYTHONPATH="/app/src${PYTHONPATH:+:$PYTHONPATH}"

exec uvicorn app:create_app --factory --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
