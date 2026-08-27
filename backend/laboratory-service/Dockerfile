# EHOS laboratory-service
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src ./src
COPY ../../shared/ehos-common ./ehos-common

RUN pip install --no-cache-dir -e ./ehos-common && \
    pip install --no-cache-dir -e .

EXPOSE 8512

CMD ["uvicorn", "laboratory_service.main:app", "--host", "0.0.0.0", "--port", "8512"]