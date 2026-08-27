"""Pytest configuration for inventory-service tests."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from inventory_service.entity.models import Base
from inventory_service.service.inventory_service import InventoryService


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
    return InventoryService()


@pytest.fixture
def actor_id():
    import uuid
    return uuid.uuid4()


@pytest.fixture
def item_id():
    import uuid
    return uuid.uuid4()
