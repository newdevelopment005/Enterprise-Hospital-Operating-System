"""Application entry point for the notification-service."""

from contextlib import asynccontextmanager

from ehos_common.api import register_exception_handlers
from ehos_common.db import Database
from ehos_common.events import KafkaProducer
from ehos_common.health import health_router
from ehos_common.idempotency import IdempotencyMiddleware, default_store
from ehos_common.logging import configure_logging
from ehos_common.metrics import MetricsMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from notification_service.api.routes import router
from notification_service.channel.adapters import build_adapters
from notification_service.configuration import get_settings
from notification_service.entity.models import Base
from notification_service.events.consumer import NotificationEventProcessor
from notification_service.events.runner import ConsumerRunner
from notification_service.service.notification_service import NotificationService


def build_event_routing() -> dict[str, dict]:
    """Map domain events to notification work orders.

    Routes only events that live producers actually publish (the old
    AppointmentCreated mapping targeted a topic nothing writes). Patient
    registration events arrive on ``clinical.patient.registered`` with the
    patient's identity but no contact channel; the notification goes to a
    configured default recipient (e.g. the admission desk) so the pipeline
    fires end to end when a producer is running.
    """
    from notification_service.configuration import get_settings
    from notification_service.dto.schemas import NotificationCreate

    def patient_registered(payload: dict) -> NotificationCreate:
        return NotificationCreate(
            template_key="patient_registered",
            recipient=payload.get("recipient") or defaults.admission_inbox,
            channel="in_app" if payload.get("recipient") is None else "email",
            variables={
                "patientId": payload.get("patientId", ""),
                "mrn": payload.get("mrn", ""),
                "name": f"{payload.get('firstName', '')} {payload.get('lastName', '')}".strip(),
            },
        )

    defaults = get_settings()
    return {
        "PatientRegistered": {
            "create": patient_registered,
            "defaultRecipient": defaults.admission_inbox,
        },
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)

    database = Database(settings.database_url)
    await database.init_models(Base)

    service = NotificationService(build_adapters(settings))
    app.state.database = database
    app.state.notification_service = service

    producer: KafkaProducer | None = None
    try:
        producer = KafkaProducer(settings.kafka_bootstrap_servers)
        await producer.start()
    except Exception:  # noqa: BLE001 - bus optional; REST delivery still works
        app.state.producer_error = True
        producer = None

    consumer = None
    runner = None
    if producer is not None:
        consumer = NotificationEventProcessor(
            settings.kafka_bootstrap_servers,
            "notification-service-group",
            service,
            database.session_factory,
            build_event_routing(),
            producer,
        )
        runner = ConsumerRunner(consumer)
        runner.start()
    app.state.consumer_runner = runner
    app.state.producer = producer

    yield

    if runner is not None:
        await runner.stop()
    if producer is not None:
        await producer.stop()
    await database.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EHOS Notification Service",
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