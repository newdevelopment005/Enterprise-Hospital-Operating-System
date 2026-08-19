"""Audit persistence service with immutable chain-of-hash integrity.

Audit records are append-only. This service verifies hash-chain integrity on
read, so any tampering with a prior record invalidates subsequent records.
"""

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from audit_service.dto.schemas import AuditRecordCreate
from audit_service.entity.models import AuditRecord

log = logging.getLogger("audit-service")


class AuditService:
    async def record(self, session: AsyncSession, data: AuditRecordCreate, event_id: str | None = None) -> AuditRecord:
        # Lock the current chain tail (FOR UPDATE, no-op on sqlite) so concurrent
        # writers cannot read the same head and fork the chain: under READ
        # COMMITTED Postgres re-evaluates the query after the lock wait and picks
        # the freshly committed row as the new tail.
        previous = (
            await session.execute(
                select(AuditRecord).order_by(AuditRecord.id.desc()).limit(1).with_for_update()
            )
        ).scalar_one_or_none()

        record = AuditRecord(
            event_id=event_id or str(uuid.uuid4()),
            event_type=data.event_type,
            actor_id=data.actor_id,
            correlation_id=data.correlation_id,
            source=data.source,
            ip_address=data.ip_address,
            action=data.action,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            old_value=data.old_value,
            new_value=data.new_value,
            reason=data.reason,
            occurred_at=data.occurred_at or datetime.now(UTC),
            previous_hash=previous.content_hash if previous else None,
        )
        record.content_hash = record.compute_hash()
        session.add(record)
        return record

    async def search(self, session: AsyncSession, filters: dict, limit: int, offset: int) -> list[AuditRecord]:
        stmt = select(AuditRecord).order_by(AuditRecord.occurred_at.desc()).limit(limit).offset(offset)
        for column, value in filters.items():
            if value:
                stmt = stmt.where(getattr(AuditRecord, column) == value)
        return list((await session.execute(stmt)).scalars().all())

    async def get(self, session: AsyncSession, record_id: int) -> AuditRecord | None:
        return (await session.execute(select(AuditRecord).where(AuditRecord.id == record_id))).scalar_one_or_none()

    async def verify_chain(self, session: AsyncSession) -> tuple[bool, str]:
        """Walk the hash chain and verify every record's integrity."""
        rows = (await session.execute(select(AuditRecord).order_by(AuditRecord.id.asc()))).scalars().all()
        previous_hash: str | None = None
        for row in rows:
            if row.previous_hash != previous_hash:
                return False, f"Broken chain at record {row.id}"
            expected = row.compute_hash()
            if expected != row.content_hash:
                return False, f"Content hash mismatch at record {row.id}"
            previous_hash = row.content_hash
        return True, "Chain integrity verified"

    async def count(self, session: AsyncSession) -> int:
        return int((await session.execute(select(func.count()).select_from(AuditRecord))).scalar_one())


def payload_to_create(envelope: dict) -> AuditRecordCreate:
    """Map an event envelope to an audit record create schema."""
    payload = envelope.get("payload", {})
    return AuditRecordCreate(
        event_type=envelope.get("eventType", "UnknownEvent"),
        actor_id=envelope.get("userId") or payload.get("actorId"),
        correlation_id=envelope.get("correlationId"),
        source=envelope.get("source", "unknown"),
        ip_address=payload.get("ipAddress"),
        action=payload.get("action"),
        resource_type=payload.get("resourceType"),
        resource_id=payload.get("resourceId"),
        old_value=json.dumps(payload["oldValue"]) if "oldValue" in payload else None,
        new_value=json.dumps(payload["newValue"]) if "newValue" in payload else None,
        reason=payload.get("reason"),
        occurred_at=envelope.get("timestamp"),
    )