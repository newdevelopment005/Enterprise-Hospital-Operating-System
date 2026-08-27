from datetime import UTC, datetime
from uuid import UUID

from ehos_common.events import DomainEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_service.dto.schemas import (
    CoverageCreate,
    CoverageUpdate,
    ClaimCreate,
    ClaimUpdate,
    PriorAuthCreate,
    PriorAuthDecision,
)
from insurance_service.entity.models import Coverage, Claim, PriorAuthorization

TOPICS = {
    "CoverageCreated": "insurance.coverage.created",
    "CoverageUpdated": "insurance.coverage.updated",
    "ClaimSubmitted": "insurance.claim.submitted",
    "ClaimAdjudicated": "insurance.claim.adjudicated",
    "PriorAuthRequested": "insurance.prior_auth.requested",
    "PriorAuthDecided": "insurance.prior_auth.decided",
}


class InsuranceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class InsuranceService:
    """Insurance service: coverage, claims, prior authorizations."""

    def __init__(self, producer: object | None = None):
        self.producer = producer

    async def _publish(self, session: AsyncSession, event_type: str, payload: dict) -> None:
        if self.producer is None:
            return
        try:
            topic = TOPICS.get(event_type)
            if topic is None:
                return
            event = DomainEvent(
                event_type=event_type,
                source="insurance-service",
                user_id=None,
                payload={"occurredAt": datetime.now(UTC).isoformat(), **payload},
            )
            outbox = session.info.get("outbox")
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await self.producer.publish(topic, event)
        except Exception:
            pass

    # ── Coverage ──────────────────────────────────────────────────────────────

    async def create_coverage(self, session: AsyncSession, payload: CoverageCreate, actor_id: UUID) -> Coverage:
        cov = Coverage(
            patient_id=payload.patient_id,
            payer_name=payload.payer_name,
            plan_name=payload.plan_name,
            policy_number=payload.policy_number,
            group_number=payload.group_number,
            coverage_type=payload.coverage_type,
            effective_date=payload.effective_date,
            termination_date=payload.termination_date,
            copay=payload.copay,
            deductible=payload.deductible,
            coinsurance=payload.coinsurance,
            is_active=payload.is_active,
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(cov)
        await session.flush()
        await self._publish(session, "CoverageCreated", {"patient_id": str(cov.patient_id), "payer": cov.payer_name})
        return cov

    async def get_coverage(self, session: AsyncSession, coverage_id: UUID) -> Coverage | None:
        return await session.get(Coverage, coverage_id)

    async def list_coverages(self, session: AsyncSession, patient_id: UUID | None = None, active_only: bool = True, limit: int = 50, offset: int = 0) -> list[Coverage]:
        stmt = select(Coverage).where(Coverage.deleted_at.is_(None))
        if patient_id:
            stmt = stmt.where(Coverage.patient_id == patient_id)
        if active_only:
            stmt = stmt.where(Coverage.is_active.is_(True))
        stmt = stmt.order_by(Coverage.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_coverage(self, session: AsyncSession, coverage_id: UUID, payload: CoverageUpdate, actor_id: UUID) -> Coverage:
        cov = await self.get_coverage(session, coverage_id)
        if not cov:
            raise InsuranceError("COVERAGE_NOT_FOUND", "Coverage not found")
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(cov, k, v)
        cov.updated_by = actor_id
        cov.model_version += 1
        await self._publish(session, "CoverageUpdated", {"coverage_id": str(cov.id)})
        return cov

    # ── Claims ────────────────────────────────────────────────────────────────

    async def create_claim(self, session: AsyncSession, payload: ClaimCreate, actor_id: UUID) -> Claim:
        claim = Claim(
            patient_id=payload.patient_id,
            coverage_id=payload.coverage_id,
            encounter_id=payload.encounter_id,
            service_date=payload.service_date,
            diagnosis_codes=payload.diagnosis_codes,
            procedure_codes=payload.procedure_codes,
            total_amount=payload.total_amount,
            status="DRAFT",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(claim)
        await session.flush()
        return claim

    async def get_claim(self, session: AsyncSession, claim_id: UUID) -> Claim | None:
        return await session.get(Claim, claim_id)

    async def list_claims(self, session: AsyncSession, patient_id: UUID | None = None, coverage_id: UUID | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> list[Claim]:
        stmt = select(Claim).where(Claim.deleted_at.is_(None))
        if patient_id:
            stmt = stmt.where(Claim.patient_id == patient_id)
        if coverage_id:
            stmt = stmt.where(Claim.coverage_id == coverage_id)
        if status:
            stmt = stmt.where(Claim.status == status)
        stmt = stmt.order_by(Claim.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def submit_claim(self, session: AsyncSession, claim_id: UUID, actor_id: UUID) -> Claim:
        claim = await self.get_claim(session, claim_id)
        if not claim:
            raise InsuranceError("CLAIM_NOT_FOUND", "Claim not found")
        if claim.status != "DRAFT":
            raise InsuranceError("INVALID_STATE", "Only DRAFT claims can be submitted")
        claim.status = "SUBMITTED"
        claim.submitted_at = datetime.now(UTC)
        claim.updated_by = actor_id
        claim.model_version += 1
        await self._publish(session, "ClaimSubmitted", {"claim_id": str(claim.id), "total": claim.total_amount})
        return claim

    async def adjudicate_claim(self, session: AsyncSession, claim_id: UUID, payload: ClaimUpdate, actor_id: UUID) -> Claim:
        claim = await self.get_claim(session, claim_id)
        if not claim:
            raise InsuranceError("CLAIM_NOT_FOUND", "Claim not found")
        if claim.status not in ("SUBMITTED", "REVIEWING"):
            raise InsuranceError("INVALID_STATE", "Only SUBMITTED/REVIEWING claims can be adjudicated")
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(claim, k, v)
        claim.adjudicated_at = datetime.now(UTC)
        claim.updated_by = actor_id
        claim.model_version += 1
        await self._publish(session, "ClaimAdjudicated", {"claim_id": str(claim.id), "status": claim.status})
        return claim

    async def update_claim(self, session: AsyncSession, claim_id: UUID, payload: ClaimUpdate, actor_id: UUID) -> Claim:
        claim = await self.get_claim(session, claim_id)
        if not claim:
            raise InsuranceError("CLAIM_NOT_FOUND", "Claim not found")
        if claim.status in ("PAID", "VOID"):
            raise InsuranceError("INVALID_STATE", f"Cannot update {claim.status} claim")
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(claim, k, v)
        claim.updated_by = actor_id
        claim.model_version += 1
        return claim

    # ── Prior Authorizations ──────────────────────────────────────────────────

    async def create_prior_auth(self, session: AsyncSession, payload: PriorAuthCreate, actor_id: UUID) -> PriorAuthorization:
        pauth = PriorAuthorization(
            patient_id=payload.patient_id,
            coverage_id=payload.coverage_id,
            service_type=payload.service_type,
            procedure_codes=payload.procedure_codes,
            clinical_justification=payload.clinical_justification,
            requested_by=payload.requested_by,
            status="PENDING",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(pauth)
        await session.flush()
        await self._publish(session, "PriorAuthRequested", {"patient_id": str(pauth.patient_id), "service_type": pauth.service_type})
        return pauth

    async def get_prior_auth(self, session: AsyncSession, prior_auth_id: UUID) -> PriorAuthorization | None:
        return await session.get(PriorAuthorization, prior_auth_id)

    async def list_prior_auths(self, session: AsyncSession, patient_id: UUID | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> list[PriorAuthorization]:
        stmt = select(PriorAuthorization).where(PriorAuthorization.deleted_at.is_(None))
        if patient_id:
            stmt = stmt.where(PriorAuthorization.patient_id == patient_id)
        if status:
            stmt = stmt.where(PriorAuthorization.status == status)
        stmt = stmt.order_by(PriorAuthorization.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def decide_prior_auth(self, session: AsyncSession, prior_auth_id: UUID, payload: PriorAuthDecision, actor_id: UUID) -> PriorAuthorization:
        pauth = await self.get_prior_auth(session, prior_auth_id)
        if not pauth:
            raise InsuranceError("PRIOR_AUTH_NOT_FOUND", "Prior authorization not found")
        if pauth.status not in ("PENDING", "SUBMITTED"):
            raise InsuranceError("INVALID_STATE", "Cannot decide on non-active prior authorization")

        pauth.decision = payload.decision
        pauth.approved_units = payload.approved_units
        pauth.valid_from = payload.valid_from
        pauth.valid_to = payload.valid_to
        pauth.denial_reason = payload.denial_reason
        pauth.decided_by = payload.decided_by
        pauth.decided_at = datetime.now(UTC)
        pauth.status = payload.decision  # APPROVED or DENIED
        pauth.updated_by = actor_id
        pauth.model_version += 1

        await self._publish(session, "PriorAuthDecided", {
            "prior_auth_id": str(pauth.id),
            "decision": pauth.decision,
        })
        return pauth

    async def cancel_prior_auth(self, session: AsyncSession, prior_auth_id: UUID, actor_id: UUID) -> PriorAuthorization:
        pauth = await self.get_prior_auth(session, prior_auth_id)
        if not pauth:
            raise InsuranceError("PRIOR_AUTH_NOT_FOUND", "Prior authorization not found")
        if pauth.status in ("APPROVED", "DENIED"):
            raise InsuranceError("INVALID_STATE", "Cannot cancel decided authorization")
        pauth.status = "CANCELLED"
        pauth.updated_by = actor_id
        pauth.model_version += 1
        return pauth


service = InsuranceService()
