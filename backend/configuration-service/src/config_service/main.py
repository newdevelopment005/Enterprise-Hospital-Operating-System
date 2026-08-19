"""Application entry point for the configuration-service.

Wires up FastAPI, the shared logging/exception handling, Kafka producer,
Redis client, and the database.
"""

from contextlib import asynccontextmanager

from ehos_common.api import register_exception_handlers
from ehos_common.db import Database
from ehos_common.events import KafkaProducer
from ehos_common.health import health_router
from ehos_common.idempotency import IdempotencyMiddleware, default_store
from ehos_common.logging import configure_logging
from ehos_common.metrics import MetricsMiddleware
from ehos_common.redis import RedisClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config_service.api.routes import router
from config_service.configuration import get_settings
from config_service.entity.models import Base
from config_service.service.configuration_service import ConfigurationService, Publisher


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)

    database = Database(settings.database_url)
    await database.init_models(Base)

    redis_client = RedisClient(settings.redis_host, settings.redis_port, settings.redis_password)
    await redis_client.start()

    producer = KafkaProducer(settings.kafka_bootstrap_servers)
    await producer.start()

    app.state.database = database
    app.state.redis = redis_client
    app.state.publisher = Publisher(producer)
    app.state.configuration_service = ConfigurationService(redis_client, app.state.publisher)

    yield

    await producer.stop()
    await redis_client.stop()
    await database.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EHOS Configuration Service",
        version=settings.service_version,
        openapi_url="/api/v1/openapi.json",
        docs_url="/docs",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(IdempotencyMiddleware, store=default_store())
    app.add_middleware(MetricsMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(router)
    return app


app = create_app()