#!/bin/sh
set -e

# В контейнере зависимости уже поставлены через uv sync.
# Локальный пакет не установлен editable — код доступен через PYTHONPATH.
export PYTHONPATH="/app/src${PYTHONPATH:+:$PYTHONPATH}"

# docker compose / kubectl command override: exec as-is
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

ROLE="${APP_ROLE:-api}"

case "$ROLE" in
  api)
    exec uvicorn app:create_app --factory \
      --host "${HOST:-0.0.0.0}" \
      --port "${PORT:-8000}"
    ;;
  outbox-worker)
    exec python -m bin.outbox_worker
    ;;
  shipment-consumer)
    exec python -m bin.shipment_consumer
    ;;
  *)
    echo "Unknown APP_ROLE='$ROLE' (expected: api|outbox-worker|shipment-consumer)" >&2
    exit 1
    ;;
esac
