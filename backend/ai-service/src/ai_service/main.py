"""Application entry point for the ai-service (HospitalGPT)."""

import asyncio
from contextlib import asynccontextmanager

from ehos_common import EventProcessor, EventRegistry, KafkaConsumer
from ehos_common.api import register_exception_handlers
from ehos_common.auth import build_auth_deps
from ehos_common.db import Database
from ehos_common.events import KafkaProducer
from ehos_common.health import health_router
from ehos_common.idempotency import IdempotencyMiddleware, default_store
from ehos_common.logging import configure_logging
from ehos_common.metrics import MetricsMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ai_service.api.routes import router
from ai_service.configuration import get_settings
from ai_service.entity.models import Base
from ai_service.service.agents import build_agent_event_handlers
from ai_service.service.ai_service import AiError, AiService


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
    except Exception:  # noqa: BLE001 - no bus in local dev; AI still works
        app.state.producer_error = True
        producer = None

    ai_service = AiService(settings)
    app.state.database = database
    app.state.settings = settings
    app.state.ai_service = ai_service
    app.state.producer = producer
    # Zero-trust: endpoints re-validate the caller's JWT (JWKS fetched lazily on
    # the first request, so a Keycloak outage fails closed with 401s).
    app.state.auth_deps = build_auth_deps(settings)

    # Event-triggered agents: consume domain events -> run the matching agent.
    processor, consumer = None, None
    event_task = None
    if producer is not None:
        handlers = build_agent_event_handlers(ai_service.agents, session_factory=database.session)
        registry = EventRegistry()
        consumer = KafkaConsumer(
            topics=registry.topics_for(list(handlers)),
            group_id="ehos-agent-triggers",
            bootstrap_servers=settings.kafka_bootstrap_servers,
        )
        try:
            await consumer.start()
            processor = EventProcessor(
                consumer=consumer,
                publisher=producer,
                registry=registry,
                handlers=handlers,
                group_id="ehos-agent-triggers",
            )
            event_task = asyncio.create_task(processor.run())
        except Exception:  # noqa: BLE001 - bus optional; agents run on-demand instead
            app.state.producer_error = True
            processor, consumer, event_task = None, None, None
    app.state.event_processor = processor

    yield

    if event_task is not None:
        event_task.cancel()
    if consumer is not None:
        await consumer.stop()
    if producer is not None:
        await producer.stop()
    await database.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EHOS AI Service (HospitalGPT)",
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

    @app.exception_handler(AiError)
    async def handle_ai_error(_request: Request, exc: AiError) -> JSONResponse:
        from datetime import UTC, datetime

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "errorCode": exc.error_code,
                "message": exc.message,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    return app


app = create_app()