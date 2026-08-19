"""Shared fixtures: in-memory async SQLite and the patient service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from patient_service.configuration import PatientSettings
from patient_service.entity.models import Base
from patient_service.service.patient_service import PatientService


@pytest.fixture
def settings() -> PatientSettings:
    s = PatientSettings()
    s.service_name = "patient-service"
    s.database_name = "ehos_patient"
    return s


@pytest.fixture
def service(settings: PatientSettings) -> PatientService:
    return PatientService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()