"""Shared fixtures: in-memory async SQLite and the queue service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from queue_service.configuration import QueueSettings
from queue_service.entity.models import Base
from queue_service.service.queue_service import QueueService


@pytest.fixture
def settings() -> QueueSettings:
    s = QueueSettings()
    s.service_name = "queue-service"
    s.database_name = "ehos_scheduling"
    return s


@pytest.fixture
def service(settings: QueueSettings) -> QueueService:
    return QueueService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()
