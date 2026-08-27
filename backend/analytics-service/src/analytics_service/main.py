"""Application entry point for the EHOS analytics-service."""

from contextlib import asynccontextmanager

from ehos_common.api import register_exception_handlers
from ehos_common.db import Database
from ehos_common.health import health_router
from ehos_common.logging import configure_logging
from ehos_common.metrics import MetricsMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from analytics_service.api.routes import router
from analytics_service.configuration import get_settings
from analytics_service.entity.models import Base
from analytics_service.service.provider import AnalyticsError, AnalyticsService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)

    database = Database(settings.database_url)
    await database.init_models(Base)

    app.state.database = database
    app.state.settings = settings
    app.state.analytics_service = AnalyticsService(settings)

    yield

    await database.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EHOS Analytics Service",
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
    app.add_middleware(MetricsMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(router)

    @app.exception_handler(AnalyticsError)
    async def handle_analytics_error(_request: Request, exc: AnalyticsError) -> JSONResponse:
        from datetime import UTC, datetime

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "errorCode": "ANALYTICS_ERROR",
                "message": exc.message,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    return app


app = create_app()
