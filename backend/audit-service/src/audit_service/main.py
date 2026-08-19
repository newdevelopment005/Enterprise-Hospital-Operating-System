"""Application entry point for the audit-service.

Exposes the audit REST API and consumes ``audit.*`` topics in the background.
"""

from contextlib import asynccontextmanager

from ehos_common.api import register_exception_handlers
from ehos_common.db import Database
from ehos_common.health import health_router
from ehos_common.idempotency import IdempotencyMiddleware, default_store
from ehos_common.logging import configure_logging
from ehos_common.metrics import MetricsMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from audit_service.api.routes import router
from audit_service.configuration import get_settings
from audit_service.entity.models import Base
from audit_service.events.consumer import AuditConsumer
from audit_service.events.runner import ConsumerRunner
from audit_service.service.audit_service import AuditService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)

    database = Database(settings.database_url)
    await database.init_models(Base)

    service = AuditService()
    app.state.database = database
    app.state.audit_service = service

    runner = ConsumerRunner(AuditConsumer(settings.kafka_bootstrap_servers, "audit-service-group", service, database))
    runner.start()
    app.state.consumer_runner = runner

    yield

    await runner.stop()
    await database.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EHOS Audit Service",
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