import uuid
from uuid import UUID

from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_service.dto.schemas import (
    CoverageCreate,
    CoverageRead,
    CoverageUpdate,
    ClaimCreate,
    ClaimRead,
    ClaimUpdate,
    PaginatedResponse,
    PriorAuthCreate,
    PriorAuthDecision,
    PriorAuthRead,
)
from insurance_service.service.insurance_service import InsuranceError, service

router = APIRouter(prefix="/api/v1/insurance", tags=["insurance"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        outbox = Outbox()
        session.info["outbox"] = outbox
        try:
            yield session
            await session.commit()
            # Publish staged events only after the write is durable; events
            # staged for a rolled-back transaction are discarded so no phantom
            # events are emitted when the DB commit fails.
            await outbox.flush(getattr(request.app.state, "producer", None))
        except Exception:
            await session.rollback()
            outbox.discard()
            raise


def get_actor(request: Request) -> UUID | None:
    raw = request.headers.get("X-User-Id")
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


# ── Coverage ────────────────────────────────────────────────────────────────────

@router.post("/coverages", response_model=CoverageRead, status_code=status.HTTP_201_CREATED)
async def create_coverage(payload: CoverageCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    return await service.create_coverage(db, payload, actor_id)


@router.get("/coverages/{coverage_id}", response_model=CoverageRead)
async def get_coverage(coverage_id: UUID, db: AsyncSession = Depends(get_session)):
    cov = await service.get_coverage(db, coverage_id)
    if not cov:
        raise HTTPException(404, "Coverage not found")
    return cov


@router.get("/coverages", response_model=PaginatedResponse)
async def list_coverages(
    patient_id: UUID | None = None, active_only: bool = True,
    limit: int = Query(50, le=200), offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    items = await service.list_coverages(db, patient_id, active_only, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/coverages/{coverage_id}", response_model=CoverageRead)
async def update_coverage(coverage_id: UUID, payload: CoverageUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_coverage(db, coverage_id, payload, actor_id)
    except InsuranceError as e:
        raise HTTPException(status_code=404 if e.code == "COVERAGE_NOT_FOUND" else 400, detail=e.message)


# ── Claims ──────────────────────────────────────────────────────────────────────

@router.post("/claims", response_model=ClaimRead, status_code=status.HTTP_201_CREATED)
async def create_claim(payload: ClaimCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    return await service.create_claim(db, payload, actor_id)


@router.get("/claims/{claim_id}", response_model=ClaimRead)
async def get_claim(claim_id: UUID, db: AsyncSession = Depends(get_session)):
    claim = await service.get_claim(db, claim_id)
    if not claim:
        raise HTTPException(404, "Claim not found")
    return claim


@router.get("/claims", response_model=PaginatedResponse)
async def list_claims(
    patient_id: UUID | None = None, coverage_id: UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200), offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    items = await service.list_claims(db, patient_id, coverage_id, status_filter, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.post("/claims/{claim_id}/submit", response_model=ClaimRead)
async def submit_claim(claim_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.submit_claim(db, claim_id, actor_id)
    except InsuranceError as e:
        raise HTTPException(status_code=404 if e.code == "CLAIM_NOT_FOUND" else 400, detail=e.message)


@router.post("/claims/{claim_id}/adjudicate", response_model=ClaimRead)
async def adjudicate_claim(claim_id: UUID, payload: ClaimUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.adjudicate_claim(db, claim_id, payload, actor_id)
    except InsuranceError as e:
        raise HTTPException(status_code=404 if e.code == "CLAIM_NOT_FOUND" else 400, detail=e.message)


@router.patch("/claims/{claim_id}", response_model=ClaimRead)
async def update_claim(claim_id: UUID, payload: ClaimUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_claim(db, claim_id, payload, actor_id)
    except InsuranceError as e:
        raise HTTPException(status_code=404 if e.code == "CLAIM_NOT_FOUND" else 400, detail=e.message)


# ── Prior Authorizations ────────────────────────────────────────────────────────

@router.post("/prior-authorizations", response_model=PriorAuthRead, status_code=status.HTTP_201_CREATED)
async def create_prior_auth(payload: PriorAuthCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    return await service.create_prior_auth(db, payload, actor_id)


@router.get("/prior-authorizations/{prior_auth_id}", response_model=PriorAuthRead)
async def get_prior_auth(prior_auth_id: UUID, db: AsyncSession = Depends(get_session)):
    pauth = await service.get_prior_auth(db, prior_auth_id)
    if not pauth:
        raise HTTPException(404, "Prior authorization not found")
    return pauth


@router.get("/prior-authorizations", response_model=PaginatedResponse)
async def list_prior_auths(
    patient_id: UUID | None = None, status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200), offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    items = await service.list_prior_auths(db, patient_id, status_filter, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.post("/prior-authorizations/{prior_auth_id}/decide", response_model=PriorAuthRead)
async def decide_prior_auth(prior_auth_id: UUID, payload: PriorAuthDecision, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.decide_prior_auth(db, prior_auth_id, payload, actor_id)
    except InsuranceError as e:
        raise HTTPException(status_code=404 if e.code == "PRIOR_AUTH_NOT_FOUND" else 400, detail=e.message)


@router.post("/prior-authorizations/{prior_auth_id}/cancel", response_model=PriorAuthRead)
async def cancel_prior_auth(prior_auth_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.cancel_prior_auth(db, prior_auth_id, actor_id)
    except InsuranceError as e:
        raise HTTPException(status_code=404 if e.code == "PRIOR_AUTH_NOT_FOUND" else 400, detail=e.message)
