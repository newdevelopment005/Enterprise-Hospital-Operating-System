"""Kafka consumer that persists audit records from all EHOS event topics.

The audit-service consumes events published by all services and writes them to
the immutable audit database with hash-chain integrity.

Rules (CODING_STANDARDS.md section 17):
- idempotent: duplicate event IDs are ignored,
- fault tolerant: a failing record is logged and processing continues,
- retry capable: network/kafka errors surface so the broker re-delivers.
"""

import asyncio
import json

import structlog
from aiokafka import AIOKafkaConsumer
from ehos_common import EventRegistry
from ehos_common.db import Database
from sqlalchemy import select

from audit_service.entity.models import AuditRecord
from audit_service.service.audit_service import AuditService, payload_to_create

log = structlog.get_logger("audit-service")

# Every topic a service may publish domain/auth/audit events on. Registry topics
# are derived from the shared catalog so the audit mirror stays in lock-step with
# the schema registry; service-specific audit topics are appended explicitly.
_REGISTRY = EventRegistry()
AUDIT_TOPICS = tuple(
    sorted({*(_REGISTRY.topic(event_type) for event_type in _REGISTRY.event_types),
            "auth.topic", "audit.topic"})
)


class AuditConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str, service: AuditService, database: Database,
                 consumer=None) -> None:
        self.service = service
        self.database = database
        self.consumer = consumer or AIOKafkaConsumer(
            *AUDIT_TOPICS,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            # raw bytes: JSON is parsed per-record so one poison pill cannot take
            # the whole batch down via the shared deserializer
            value_deserializer=None,
        )
        self._running = True

    async def run(self) -> None:
        await self.consumer.start()
        try:
            while self._running:
                try:
                    batch = await self.consumer.getmany(timeout_ms=2000, max_records=200)
                except Exception:  # noqa: BLE001 - transient broker errors must not kill the loop
                    log.exception("consumer getmany failed; waiting for redelivery")
                    await asyncio.sleep(2)
                    continue
                for _topic_partition, messages in batch.items():
                    for message in messages:
                        await self._process(message)
                await self.consumer.commit()
        finally:
            await self.consumer.stop()

    async def _process(self, message) -> None:
        try:
            value = message.value
            envelope: dict = json.loads(value.decode("utf-8")) if isinstance(value, (bytes, bytearray)) else value
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, AttributeError):
            log.exception("malformed audit message skipped", topic=getattr(message, "topic", "?"),
                          partition=getattr(message, "partition", None), offset=getattr(message, "offset", None))
            return
        event_id = envelope.get("eventId", "")
        async with self.database.session() as session:
            try:
                existing = (
                    await session.execute(select(AuditRecord).where(AuditRecord.event_id == event_id))
                ).scalar_one_or_none()
                if existing is not None:
                    return
                record = await self.service.record(session, payload_to_create(envelope), event_id=event_id)
                await session.commit()
                log.info("audit_record_written", eventId=record.event_id, eventType=record.event_type)
            except Exception:
                await session.rollback()
                log.exception("failed to process audit event", eventId=event_id)

    def stop(self) -> None:
        self._running = False