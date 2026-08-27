"""Shared fixtures: in-memory async SQLite and the billing service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from billing_service.configuration import BillingSettings
from billing_service.entity.models import Base
from billing_service.service.billing_service import BillingService


@pytest.fixture
def settings() -> BillingSettings:
    s = BillingSettings()
    s.service_name = "billing-service"
    s.database_name = "ehos_billing"
    return s


@pytest.fixture
def service(settings: BillingSettings) -> BillingService:
    return BillingService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()
