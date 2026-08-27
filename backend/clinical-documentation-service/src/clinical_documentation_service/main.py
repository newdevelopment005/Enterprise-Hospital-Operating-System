"""Application entry point for the clinical-documentation-service.

Wires up FastAPI, logging, the private database, the documentation service, and
an optional Kafka producer (local development runs without a bus).
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

from clinical_documentation_service.api.routes import router
from clinical_documentation_service.configuration import settings
from clinical_documentation_service.entity.models import Base
from clinical_documentation_service.service.documentation_service import DocumentationError, service


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings)

    database = Database(settings.database_url)
    await database.init_models(Base)

    producer: KafkaProducer | None = None
    try:
        producer = KafkaProducer(settings.kafka_bootstrap_servers)
        await producer.start()
    except Exception:  # noqa: BLE001 - no bus in local dev; requests still work
        app.state.producer_error = True
        producer = None

    service.producer = producer

    app.state.database = database
    app.state.settings = settings
    app.state.producer = producer

    yield

    if producer is not None:
        await producer.stop()
    await database.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="EHOS Clinical Documentation Service",
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

    @app.exception_handler(DocumentationError)
    async def handle_documentation_error(_request: Request, exc: DocumentationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "errorCode": exc.code,
                "message": exc.message,
                "timestamp": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
            },
        )

    return app


app = create_app()