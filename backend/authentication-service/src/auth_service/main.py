"""Application entry point for the authentication-service.

Wires up FastAPI, shared logging and exception handling, the database, and the
service graph (tokens, passwords, MFA, RBAC, ABAC, authentication). Kafka is
started lazily/optional so local development runs without an event bus.
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

from auth_service.api.routes import router
from auth_service.configuration import get_settings
from auth_service.entity.models import Base
from auth_service.service.abac_service import AbacService
from auth_service.service.auth_service import AuthenticationService, AuthServiceError
from auth_service.service.mfa_service import MfaService
from auth_service.service.password_service import PasswordService
from auth_service.service.rbac_service import RbacService
from auth_service.service.token_service import TokenService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)

    database = Database(settings.database_url)
    await database.init_models(Base)

    token_service = TokenService(settings)
    password_service = PasswordService(settings)
    mfa_service = MfaService(settings)
    rbac_service = RbacService()
    abac_service = AbacService()

    producer: KafkaProducer | None = None
    try:
        producer = KafkaProducer(settings.kafka_bootstrap_servers)
        await producer.start()
    except Exception:  # noqa: BLE001 - no bus in local dev; authentication still works
        app.state.producer_error = True
        producer = None

    auth_service = AuthenticationService(
        settings, token_service, password_service, mfa_service, rbac_service, producer=producer
    )

    app.state.database = database
    app.state.settings = settings
    app.state.token_service = token_service
    app.state.password_service = password_service
    app.state.mfa_service = mfa_service
    app.state.rbac_service = rbac_service
    app.state.abac_service = abac_service
    app.state.auth_service = auth_service
    app.state.producer = producer

    yield

    if producer is not None:
        await producer.stop()
    await database.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EHOS Authentication Service",
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

    @app.exception_handler(AuthServiceError)
    async def handle_auth_error(_request: Request, exc: AuthServiceError) -> JSONResponse:
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