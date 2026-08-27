"""Shared fixtures: in-memory async SQLite and the pharmacy service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pharmacy_service.configuration import PharmacySettings
from pharmacy_service.entity.models import Base
from pharmacy_service.service.pharmacy_service import PharmacyService


@pytest.fixture
def settings() -> PharmacySettings:
    s = PharmacySettings()
    s.service_name = "pharmacy-service"
    s.database_name = "ehos_pharmacy"
    return s


@pytest.fixture
def service(settings: PharmacySettings) -> PharmacyService:
    return PharmacyService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()
