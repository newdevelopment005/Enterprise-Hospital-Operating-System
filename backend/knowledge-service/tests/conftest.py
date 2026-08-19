"""Shared fixtures: in-memory async SQLite and the knowledge-service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from knowledge_service.configuration import KnowledgeSettings
from knowledge_service.entity.models import Base
from knowledge_service.service.knowledge_service import KnowledgeService


@pytest.fixture
def settings() -> KnowledgeSettings:
    s = KnowledgeSettings()
    s.service_name = "knowledge-service"
    s.database_name = "ehos_knowledge"
    return s


@pytest.fixture
def service(settings: KnowledgeSettings) -> KnowledgeService:
    return KnowledgeService(settings)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()