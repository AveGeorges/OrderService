FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .

RUN addgroup --system --gid 1000 appuser \
    && adduser --system --uid 1000 --ingroup appuser --no-create-home appuser \
    && mkdir -p /app/logs /app/.cache/uv \
    && chmod +x /app/scripts/entrypoint.sh \
    && chown -R appuser:appuser /app

ENV HOME=/app \
    UV_CACHE_DIR=/app/.cache/uv

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
