"""Shared fixtures: in-memory async SQLite and the analytics service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from analytics_service.configuration import AnalyticsSettings
from analytics_service.entity.models import Base
from analytics_service.service.provider import AnalyticsService


@pytest.fixture
def settings() -> AnalyticsSettings:
    s = AnalyticsSettings()
    s.service_name = "analytics-service"
    s.database_name = "ehos_analytics"
    return s


@pytest.fixture
def service(settings: AnalyticsSettings) -> AnalyticsService:
    return AnalyticsService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()
