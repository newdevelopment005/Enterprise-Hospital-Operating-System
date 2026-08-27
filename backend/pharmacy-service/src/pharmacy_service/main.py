"""Application entry point for the pharmacy-service.

Wires up FastAPI, logging, database, the pharmacy service, and optional Kafka
producer for dispensing events (local development runs without a bus).
"""

from contextlib import asynccontextmanager

from ehos_common.api import register_exception_handlers
from ehos_common.db import Database
from ehos_common.events import KafkaProducer
from ehos_common.health import health_router
from ehos_common.idempotency import IdempotencyMiddleware, default_store
from ehos_common.logging import configure_logging
from ehos_common.metrics import MetricsMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pharmacy_service.api.routes import router
from pharmacy_service.configuration import get_settings
from pharmacy_service.entity.models import Base
from pharmacy_service.service.pharmacy_service import PharmacyError, PharmacyService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)

    database = Database(settings.database_url)
    await database.init_models(Base)

    producer: KafkaProducer | None = None
    try:
        producer = KafkaProducer(settings.kafka_bootstrap_servers)
        await producer.start()
    except Exception:  # noqa: BLE001 - no bus in local dev; dispensing still works
        app.state.producer_error = True
        producer = None

    app.state.database = database
    app.state.settings = settings
    app.state.pharmacy_service = PharmacyService(settings, producer=producer)
    app.state.producer = producer

    yield

    if producer is not None:
        await producer.stop()
    await database.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EHOS Pharmacy Service",
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

    @app.exception_handler(PharmacyError)
    async def handle_pharmacy_error(_request: Request, exc: PharmacyError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "errorCode": exc.error_code,
                "message": exc.message,
                "timestamp": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
            },
        )

    return app


app = create_app()
