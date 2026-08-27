"""Shared fixtures: in-memory async SQLite and the prescription service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from prescription_service.configuration import PrescriptionSettings
from prescription_service.entity.models import Base
from prescription_service.service.prescription_service import PrescriptionService


@pytest.fixture
def settings() -> PrescriptionSettings:
    s = PrescriptionSettings()
    s.service_name = "prescription-service"
    s.database_name = "ehos_prescription"
    return s


@pytest.fixture
def service(settings: PrescriptionSettings) -> PrescriptionService:
    return PrescriptionService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()
