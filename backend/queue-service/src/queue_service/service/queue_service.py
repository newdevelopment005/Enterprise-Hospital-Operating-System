"""Business logic for the digital queues: create, join, call-next, serve.

Publishes ``QueueJoined`` / ``QueueAdvanced`` / ``QueueCompleted`` on
``clinical.queue.*`` so displays, analytics and notification services keep
projections fresh (EHOS_ARCHITECTURE_DESIGN.md section 3.2).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from ehos_common.events import DomainEvent
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from queue_service.configuration import QueueSettings
from queue_service.dto.schemas import JoinIn, QueueIn
from queue_service.entity.models import Queue, QueueEntry

log = logging.getLogger("queue-service")

QUEUE_JOINED_TOPIC = "clinical.queue.joined"
QUEUE_ADVANCED_TOPIC = "clinical.queue.advanced"
QUEUE_COMPLETED_TOPIC = "clinical.queue.completed"

_QUEUE_TOPICS = {
    "QueueJoined": QUEUE_JOINED_TOPIC,
    "QueueAdvanced": QUEUE_ADVANCED_TOPIC,
    "QueueCompleted": QUEUE_COMPLETED_TOPIC,
}

# ticket prefixes per queue type
TICKET_PREFIX = {
    "OUTPATIENT": "OP",
    "EMERGENCY": "ER",
    "LAB": "LB",
    "PHARMACY": "PH",
    "ADMISSION": "AD",
    "RADIOLOGY": "RD",
}

WAITING_STATUSES = ("WAITING",)
OPEN_STATUSES = ("WAITING", "CALLED", "IN_PROGRESS")


class QueueError(Exception):
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class QueueService:
    def __init__(self, settings: QueueSettings, producer=None):
        self.settings = settings
        self.producer = producer

    # ------------------------------------------------------------ helpers

    async def _publish(self, session: AsyncSession, event_type: str, payload: dict) -> None:
        if self.producer is None:
            return
        try:
            topic = _QUEUE_TOPICS.get(event_type, QUEUE_JOINED_TOPIC)
            event = DomainEvent(
                event_type=event_type,
                source="queue-service",
                user_id=None,
                payload={"occurredAt": datetime.now(UTC).isoformat(), **payload},
            )
            outbox = session.info.get("outbox")
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await self.producer.publish(topic, event)
        except Exception:  # noqa: BLE001 - publishing must never break queuing
            log.exception("failed to publish %s", event_type)

    async def _get_queue(self, session: AsyncSession, queue_id) -> Queue:
        queue = await session.get(Queue, queue_id)
        if queue is None or queue.deleted_at is not None:
            raise QueueError("QUEUE_NOT_FOUND", "Queue not found", 404)
        return queue

    async def _get_entry(self, session: AsyncSession, entry_id) -> QueueEntry:
        entry = await session.get(QueueEntry, entry_id)
        if entry is None or entry.deleted_at is not None:
            raise QueueError("ENTRY_NOT_FOUND", "Queue entry not found", 404)
        return entry

    async def _next_ticket(self, session: AsyncSession, queue: Queue) -> str:
        prefix = TICKET_PREFIX.get(queue.queue_type, "Q")
        result = await session.execute(
            select(func.count()).select_from(QueueEntry).where(QueueEntry.queue_id == queue.id)
        )
        seq = result.scalar_one()
        return f"{prefix}-{seq + 1:0{self.settings.ticket_width}d}"

    # ------------------------------------------------------------ queues

    async def create_queue(self, session: AsyncSession, data: QueueIn, actor=None) -> Queue:
        department_id = uuid.UUID(data.department_id) if data.department_id else None
        queue = Queue(
            queue_type=data.queue_type,
            name=data.name or data.queue_type.title(),
            department_id=department_id,
            is_active=True,
            created_by=actor,
            status="ACTIVE",
        )
        session.add(queue)
        await session.flush()
        return queue

    async def list_queues(self, session: AsyncSession, active_only: bool = True) -> list[Queue]:
        stmt = select(Queue).where(Queue.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(Queue.is_active.is_(True))
        rows = (await session.execute(stmt.order_by(Queue.created_at))).scalars().all()
        return list(rows)

    async def queue_board(self, session: AsyncSession, queue_id) -> dict:
        """Queue snapshot: counts per status plus the current waiting list."""
        queue = await self._get_queue(session, queue_id)
        entries = (
            (
                await session.execute(
                    select(QueueEntry)
                    .where(
                        QueueEntry.queue_id == queue.id,
                        QueueEntry.deleted_at.is_(None),
                        QueueEntry.status.in_((*OPEN_STATUSES, "COMPLETED", "SKIPPED", "CANCELLED")),
                    )
                    .order_by(QueueEntry.joined_at)
                )
            )
            .scalars()
            .all()
        )
        waiting = [e for e in entries if e.status in WAITING_STATUSES]
        serving = next((e for e in reversed(entries) if e.status in ("CALLED", "IN_PROGRESS")), None)
        counts: dict[str, int] = {}
        for e in entries:
            counts[e.status] = counts.get(e.status, 0) + 1
        now_serving = _entry_out(serving) if serving else None
        return {
            "queue": _queue_out(queue),
            "now_serving": now_serving,
            "waiting": [_entry_out(e) for e in waiting],
            "counts": counts,
        }

    # ------------------------------------------------------------ entries

    async def join(
        self, session: AsyncSession, queue_id, data: JoinIn, actor=None
    ) -> QueueEntry:
        queue = await self._get_queue(session, queue_id)
        if not queue.is_active:
            raise QueueError("QUEUE_CLOSED", "This queue is not accepting tickets.", 409)

        patient_id = uuid.UUID(data.patient_id)
        # one open ticket per patient per queue
        existing = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.queue_id == queue.id,
                    QueueEntry.patient_id == patient_id,
                    QueueEntry.deleted_at.is_(None),
                    QueueEntry.status.in_(OPEN_STATUSES),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise QueueError(
                "ALREADY_IN_QUEUE",
                f"Patient already holds ticket {existing.ticket_number} in this queue.",
                409,
            )

        entry = QueueEntry(
            queue_id=queue.id,
            patient_id=patient_id,
            patient_snapshot=data.patient_snapshot,
            ticket_number=await self._next_ticket(session, queue),
            priority=data.priority,
            status="WAITING",
        )
        session.add(entry)
        await session.flush()
        await self._publish(
            session,
            "QueueJoined",
            {
                "queueId": str(queue.id),
                "entryId": str(entry.id),
                "patientId": str(patient_id),
                "ticketNumber": entry.ticket_number,
            },
        )
        return entry

    async def advance(self, session: AsyncSession, queue_id, actor=None) -> QueueEntry:
        """Call the next ticket: highest priority first, then earliest joined."""
        queue = await self._get_queue(session, queue_id)
        entry = (
            await session.execute(
                select(QueueEntry)
                .where(
                    QueueEntry.queue_id == queue.id,
                    QueueEntry.deleted_at.is_(None),
                    QueueEntry.status == "WAITING",
                )
                .order_by(QueueEntry.priority.desc(), QueueEntry.joined_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if entry is None:
            raise QueueError("QUEUE_EMPTY", "No patients are waiting in this queue.", 409)

        # finish any ticket left hanging in CALLED (missed) as SKIPPED
        hanging = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.queue_id == queue.id,
                    QueueEntry.deleted_at.is_(None),
                    QueueEntry.status == "CALLED",
                )
            )
        ).scalars().all()
        for h in hanging:
            h.status = "SKIPPED"

        entry.status = "CALLED"
        entry.called_at = datetime.now(UTC)
        entry.version += 1
        entry.updated_by = actor
        await session.flush()
        await self._publish(
            session,
            "QueueAdvanced",
            {"queueId": str(queue.id), "entryId": str(entry.id), "ticketNumber": entry.ticket_number},
        )
        return entry

    async def start(self, session: AsyncSession, entry_id, actor=None) -> QueueEntry:
        entry = await self._get_entry(session, entry_id)
        if entry.status != "CALLED":
            raise QueueError("INVALID_STATUS", f"Cannot start a ticket with status {entry.status}.", 409)
        entry.status = "IN_PROGRESS"
        entry.started_at = datetime.now(UTC)
        entry.served_by = actor
        entry.version += 1
        await session.flush()
        return entry

    async def complete(self, session: AsyncSession, entry_id, actor=None) -> QueueEntry:
        entry = await self._get_entry(session, entry_id)
        if entry.status not in ("CALLED", "IN_PROGRESS"):
            raise QueueError("INVALID_STATUS", f"Cannot complete a ticket with status {entry.status}.", 409)
        now = datetime.now(UTC)
        entry.status = "COMPLETED"
        entry.completed_at = now
        joined = entry.joined_at if entry.joined_at.tzinfo else entry.joined_at.replace(tzinfo=UTC)
        entry.wait_time_min = max(0, int((now - joined).total_seconds() // 60))
        entry.version += 1
        await session.flush()
        await self._publish(
            session,
            "QueueCompleted",
            {"queueId": str(entry.queue_id), "entryId": str(entry.id), "waitTimeMin": entry.wait_time_min},
        )
        return entry

    async def cancel(self, session: AsyncSession, entry_id, reason: str | None, actor=None) -> QueueEntry:
        entry = await self._get_entry(session, entry_id)
        if entry.status in ("COMPLETED", "CANCELLED"):
            raise QueueError("INVALID_STATUS", f"Cannot cancel a ticket with status {entry.status}.", 409)
        entry.status = "CANCELLED"
        entry.deletion_reason = reason
        entry.updated_by = actor
        entry.version += 1
        await session.flush()
        return entry


# ---------------------------------------------------------------- serializers

def _queue_out(q: Queue) -> dict:
    return {
        "id": str(q.id),
        "queue_type": q.queue_type,
        "name": q.name,
        "department_id": str(q.department_id) if q.department_id else None,
        "is_active": q.is_active,
        "created_at": q.created_at.isoformat(),
    }


def _entry_out(e: QueueEntry) -> dict:
    return {
        "id": str(e.id),
        "queue_id": str(e.queue_id),
        "patient_id": str(e.patient_id),
        "ticket_number": e.ticket_number,
        "priority": e.priority,
        "status": e.status,
        "joined_at": e.joined_at.isoformat(),
        "called_at": e.called_at.isoformat() if e.called_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        "wait_time_min": e.wait_time_min,
    }
