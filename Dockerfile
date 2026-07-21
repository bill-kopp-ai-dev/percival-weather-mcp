# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build
RUN pip install --no-cache-dir uv==0.5.7
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv export --format requirements-txt --no-hashes --no-dev > /tmp/requirements.txt \
 && uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python -r /tmp/requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}"

RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY --chown=app:app src ./src
USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request, sys; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"] || exit 1

CMD ["python", "-m", "percival_weather_mcp", "--mode", "streamable-http", "--host", "0.0.0.0", "--port", "8080"]
