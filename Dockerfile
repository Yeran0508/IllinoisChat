FROM python:3.12.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RUFF_CACHE_DIR=/tmp/ruff_cache \
    COVERAGE_FILE=/tmp/.coverage

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend

RUN python -m pip install --no-cache-dir .

RUN addgroup --system app && adduser --system --ingroup app app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS test

USER root
RUN python -m pip install --no-cache-dir ".[dev]"
USER app

CMD ["pytest"]
