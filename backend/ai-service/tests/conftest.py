"""Shared fixtures: in-memory async SQLite and the ai-service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ai_service.configuration import AiSettings
from ai_service.entity.models import Base
from ai_service.service.ai_service import AiService


@pytest.fixture
def settings() -> AiSettings:
    s = AiSettings()
    s.service_name = "ai-service"
    s.database_name = "ehos_ai"
    return s


@pytest.fixture
def service(settings: AiSettings) -> AiService:
    return AiService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()