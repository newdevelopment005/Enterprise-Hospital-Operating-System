import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from insurance_service.entity.models import Base
from insurance_service.service.insurance_service import InsuranceService

TEST_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def fresh_engine():
    engine = create_async_engine(TEST_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(fresh_engine):
    session_factory = async_sessionmaker(fresh_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
def ins_service():
    return InsuranceService()
