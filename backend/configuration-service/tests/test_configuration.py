"""Unit tests for the configuration service business logic."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config_service.dto.schemas import ConfigurationEntryIn, FeatureFlagIn
from config_service.entity.models import Base
from config_service.service.configuration_service import ConfigurationService


class FakeRedisCache:
    def __init__(self):
        self.store: dict[str, object] = {}
        self.ttl: dict[str, int] = {}

    async def set_json(self, key: str, value: object, ttl_seconds: int | None = None) -> None:
        self.store[key] = value
        if ttl_seconds:
            self.ttl[key] = ttl_seconds

    async def get_json(self, key: str) -> object | None:
        return self.store.get(key)

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class FakePublisher:
    def __init__(self):
        self.events: list[tuple[str, str]] = []

    async def publish_configuration_updated(self, config_key: str, value: object, user_id: str | None = None) -> None:
        self.events.append((config_key, value))


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def service():
    redis = FakeRedisCache()
    publisher = FakePublisher()
    return ConfigurationService(redis, publisher), publisher


async def test_create_flag(session, service):
    svc, _ = service
    data = FeatureFlagIn(name="exact_dose_required", enabled=True, description="Policy")
    await svc.create_flag(session, data, updated_by="admin")
    await session.commit()
    result = await session.execute(Base.metadata.tables["feature_flags"].select())
    rows = result.fetchall()
    assert len(rows) == 1
    assert rows[0].enabled is True


async def test_upsert_entry_creates_and_updates(session, service):
    svc, publisher = service
    data = ConfigurationEntryIn(
        config_key="appointment_slot_min", config_value={"minutes": 15}, value_type="int"
    )
    first = await svc.upsert_entry(session, data, updated_by="admin")
    assert first.version == 1
    data.config_value = {"minutes": 20}
    second = await svc.upsert_entry(session, data, updated_by="admin")
    assert second.version == 2
    assert [key for key, _ in publisher.events] == ["appointment_slot_min", "appointment_slot_min"]


async def test_set_flag_not_found(session, service):
    svc, _ = service
    assert await svc.set_flag(session, "missing", True, updated_by=None) is None