"""Shared fixtures: in-memory async SQLite and the ehr-service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ehr_service.configuration import EhrSettings
from ehr_service.entity.models import Base
from ehr_service.service.ehr_service import EhrService


@pytest.fixture
def settings() -> EhrSettings:
    s = EhrSettings()
    s.service_name = "ehr-service"
    s.database_name = "ehos_ehr"
    return s


@pytest.fixture
def service(settings: EhrSettings) -> EhrService:
    return EhrService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()