FROM python:3.12.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RUFF_CACHE_DIR=/tmp/ruff_cache \
    COVERAGE_FILE=/tmp/.coverage \
    HOME=/tmp/app-home \
    XDG_CACHE_HOME=/tmp/app-cache

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY data/evaluation ./data/evaluation
COPY data/sample ./data/sample
COPY alembic.ini ./
COPY migrations ./migrations

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

FROM node:24.11.0-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM nginx:1.29.3-alpine AS frontend

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /frontend/dist /usr/share/nginx/html
EXPOSE 8080
