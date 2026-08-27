"""Pytest configuration for radiology-service tests."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from radiology_service.entity.models import Base
from radiology_service.service.radiology_service import RadiologyService


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def svc():
    return RadiologyService()


@pytest.fixture
def actor_id():
    import uuid
    return uuid.uuid4()


@pytest.fixture
def patient_id():
    import uuid
    return uuid.uuid4()


@pytest.fixture
def doctor_id():
    import uuid
    return uuid.uuid4()
