"""Shared fixtures: in-memory async SQLite and the appointment service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from appointment_service.configuration import AppointmentSettings
from appointment_service.entity.models import Base
from appointment_service.service.appointment_service import AppointmentService


@pytest.fixture
def settings() -> AppointmentSettings:
    s = AppointmentSettings()
    s.service_name = "appointment-service"
    s.database_name = "ehos_scheduling"
    return s


@pytest.fixture
def service(settings: AppointmentSettings) -> AppointmentService:
    return AppointmentService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()
