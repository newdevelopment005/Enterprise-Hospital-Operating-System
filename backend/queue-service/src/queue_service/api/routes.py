"""REST API for the queue-service.

Endpoints under ``/api/v1/queues`` return the standard EHOS envelope. The
service sits behind the API gateway which injects the OAuth2 token.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from ehos_common.api import success_response
from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from queue_service.dto.schemas import JoinIn, PriorityIn, QueueIn
from queue_service.service.queue_service import (
    QueueError,
    QueueService,
    _entry_out,
    _queue_out,
)

router = APIRouter(prefix="/api/v1/queues", tags=["queues"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        outbox = Outbox()
        session.info["outbox"] = outbox
        try:
            yield session
            await session.commit()
            # Publish staged events only after the write is durable; events
            # staged for a rolled-back transaction are discarded (no phantom
            # events when the DB commit fails).
            await outbox.flush(getattr(request.app.state, "producer", None))
        except Exception:
            await session.rollback()
            outbox.discard()
            raise


def get_service(request: Request) -> QueueService:
    return request.app.state.queue_service


SvcDep = Annotated[QueueService, Depends(get_service)]


# ================================================================== queues

@router.post("", status_code=201)
async def create_queue(
    data: QueueIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    queue = await svc.create_queue(session, data)
    return success_response(_queue_out(queue))


@router.get("")
async def list_queues(
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rows = await svc.list_queues(session, active_only=active_only)
    return success_response({"queues": [_queue_out(q) for q in rows], "total": len(rows)})


# NOTE: static paths are declared before /{queue_id} so they never shadow it.

@router.get("/board/{queue_id}")
async def queue_board(
    queue_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    return success_response(await svc.queue_board(session, _uuid(queue_id)))


@router.post("/{queue_id}/entries", status_code=201)
async def join_queue(
    queue_id: str,
    data: JoinIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    entry = await svc.join(session, _uuid(queue_id), data)
    return success_response(_entry_out(entry))


@router.post("/{queue_id}/advance")
async def advance_queue(
    queue_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    entry = await svc.advance(session, _uuid(queue_id))
    return success_response(_entry_out(entry))


@router.get("/{queue_id}")
async def get_queue(
    queue_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    queue = await svc._get_queue(session, _uuid(queue_id))  # noqa: SLF001
    return success_response(_queue_out(queue))


# ================================================================== entries

@router.post("/entries/{entry_id}/start")
async def start_entry(
    entry_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    entry = await svc.start(session, _uuid(entry_id))
    return success_response(_entry_out(entry))


@router.post("/entries/{entry_id}/complete")
async def complete_entry(
    entry_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    entry = await svc.complete(session, _uuid(entry_id))
    return success_response(_entry_out(entry))


@router.post("/entries/{entry_id}/cancel")
async def cancel_entry(
    entry_id: str,
    reason: str | None = Query(default=None, max_length=500),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    entry = await svc.cancel(session, _uuid(entry_id), reason)
    return success_response(_entry_out(entry))


@router.patch("/entries/{entry_id}/priority")
async def set_priority(
    entry_id: str,
    data: PriorityIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    entry = await svc._get_entry(session, _uuid(entry_id))  # noqa: SLF001
    if entry.status not in ("WAITING",):
        raise QueueError("INVALID_STATUS", "Priority can only be changed while waiting.", 409)
    entry.priority = data.priority
    entry.version += 1
    await session.flush()
    return success_response(_entry_out(entry))


# ================================================================== helpers

def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise QueueError("INVALID_ID", f"Invalid identifier: {value}", 422) from exc
