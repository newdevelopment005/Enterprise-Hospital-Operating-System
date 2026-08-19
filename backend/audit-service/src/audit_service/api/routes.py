"""REST API for the audit-service.

Read and create audit records. Records are immutable (no update/delete endpoints).
"""

from collections.abc import AsyncIterator

from ehos_common.api import NotFoundError, success_response
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from audit_service.dto.schemas import AuditRecordCreate
from audit_service.service.audit_service import AuditService

router = APIRouter(prefix="/api/v1", tags=["audit"])


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_service(request: Request) -> AuditService:
    return request.app.state.audit_service


SERVICE = Depends(get_service)


@router.post("/records", status_code=status.HTTP_201_CREATED)
async def create_record(
    data: AuditRecordCreate,
    session: AsyncSession = Depends(get_session),
    service: AuditService = SERVICE,
) -> dict:
    record = await service.record(session, data)
    return success_response(record)


@router.get("/records/{record_id}")
async def get_record(
    record_id: int,
    session: AsyncSession = Depends(get_session),
    service: AuditService = SERVICE,
) -> dict:
    record = await service.get(session, record_id)
    if record is None:
        raise NotFoundError(f"Audit record {record_id} not found")
    return success_response(record)


@router.get("/records")
async def search_records(
    event_type: str | None = None,
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    service: AuditService = SERVICE,
) -> dict:
    records = await service.search(
        session,
        {"event_type": event_type, "actor_id": actor_id, "resource_type": resource_type, "resource_id": resource_id},
        limit=limit,
        offset=offset,
    )
    return success_response(records)


@router.get("/integrity")
async def verify_integrity(
    session: AsyncSession = Depends(get_session),
    service: AuditService = SERVICE,
) -> dict:
    """Verifies the append-only hash chain across all audit records."""
    valid, message = await service.verify_chain(session)
    count = await service.count(session)
    return success_response({"valid": valid, "message": message, "records": count})