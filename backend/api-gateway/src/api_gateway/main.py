"""FastAPI entry point for the API gateway."""

from contextlib import asynccontextmanager

from ehos_common.api import register_exception_handlers
from ehos_common.health import health_router
from ehos_common.logging import configure_logging
from ehos_common.metrics import MetricsMiddleware
from ehos_common.redis import RateLimiterRedis
from ehos_common.security import get_verifier
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_gateway.configuration import get_settings
from api_gateway.proxy.handler import proxy_router
from api_gateway.security.middleware import AuthMiddleware, RateLimitMiddleware, RequestIdMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)

    redis_client = RateLimiterRedis(
        host=settings.redis_host, port=settings.redis_port, password=settings.redis_password
    )
    verifier = get_verifier(settings.jwks_url, settings.issuer, "account")

    app.state.redis = redis_client
    app.state.verifier = verifier
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EHOS API Gateway",
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
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(MetricsMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(proxy_router)
    return app


app = create_app()