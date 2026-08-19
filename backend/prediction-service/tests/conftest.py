"""Shared fixtures: in-memory async SQLite and the prediction service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from prediction_service.configuration import PredictionSettings
from prediction_service.entity.models import Base
from prediction_service.service.provider import PredictionService


@pytest.fixture
def settings() -> PredictionSettings:
    s = PredictionSettings()
    s.service_name = "prediction-service"
    s.database_name = "ehos_ai"
    return s


@pytest.fixture
def service(settings: PredictionSettings) -> PredictionService:
    return PredictionService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()