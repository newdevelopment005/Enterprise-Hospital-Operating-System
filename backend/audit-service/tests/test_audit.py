"""Tests for the audit-service hash-chain integrity."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from audit_service.entity.models import AuditRecord, Base
from audit_service.service.audit_service import AuditService


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _record(event_id: str, event_type: str, previous_hash: str | None = None) -> AuditRecord:
    record = AuditRecord(
        event_id=event_id,
        event_type=event_type,
        source="t",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        previous_hash=previous_hash,
    )
    record.content_hash = record.compute_hash()
    return record


async def test_chain_is_linked(session):
    service = AuditService()
    first = _record("e1", "A")
    second = _record("e2", "B", previous_hash=first.content_hash)
    session.add_all([first, second])
    await session.flush()
    valid, message = await service.verify_chain(session)
    assert valid, message


async def test_detects_tampering(session):
    service = AuditService()
    first = _record("e1", "A")
    second = _record("e2", "B", previous_hash=first.content_hash)
    session.add_all([first, second])
    await session.flush()
    valid, _ = await service.verify_chain(session)
    assert valid is True
    first.action = "tampered"
    await session.commit()
    valid, message = await service.verify_chain(session)
    assert valid is False
    assert "Content hash mismatch" in message


async def test_chain_survives_db_round_trip(session):
    """Naive datetimes returned by sqlite must not invalidate the hashes.

    The content hash canonicalizes ``occurred_at`` to aware-UTC isoformat, so a
    record written with an aware datetime and re-read as naive still verifies.
    """
    service = AuditService()
    first = _record("e1", "A")
    second = _record("e2", "B", previous_hash=first.content_hash)
    session.add_all([first, second])
    await session.commit()
    # drop identity-map state so occurred_at comes back from the DB (naive here)
    session.expunge_all()

    valid, message = await service.verify_chain(session)
    assert valid, message