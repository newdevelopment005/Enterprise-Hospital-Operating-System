FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY shared/ehos-common /opt/ehos-common
RUN pip install /opt/ehos-common

COPY backend/configuration-service/pyproject.toml /app/service/pyproject.toml
COPY backend/configuration-service/src /app/service/src
WORKDIR /app/service
RUN pip install .

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/docs', timeout=3)"

CMD ["uvicorn", "config_service.main:app", "--host", "0.0.0.0", "--port", "8100"]