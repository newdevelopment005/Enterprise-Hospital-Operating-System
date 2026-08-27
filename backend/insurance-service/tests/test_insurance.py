import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_service.dto.schemas import (
    CoverageCreate,
    CoverageUpdate,
    ClaimCreate,
    ClaimUpdate,
    PriorAuthCreate,
    PriorAuthDecision,
)
from insurance_service.service.insurance_service import InsuranceService, InsuranceError


def _uid():
    return uuid.uuid4()


def _cov_payload(**overrides):
    d = dict(patient_id=_uid(), payer_name="Blue Cross", policy_number="POL-001", coverage_type="HEALTH", effective_date="2025-01-01")
    d.update(overrides)
    return CoverageCreate(**d)


def _claim_payload(**overrides):
    d = dict(patient_id=_uid(), coverage_id=_uid(), service_date="2025-06-01", total_amount=100.0)
    d.update(overrides)
    return ClaimCreate(**d)


def _pauth_payload(**overrides):
    d = dict(patient_id=_uid(), coverage_id=_uid(), service_type="SURGERY", requested_by=_uid())
    d.update(overrides)
    return PriorAuthCreate(**d)


# ── Coverage ────────────────────────────────────────────────────────────────────


class TestCoverage:
    async def test_create_coverage(self, db: AsyncSession, ins_service: InsuranceService):
        cov = await ins_service.create_coverage(db, _cov_payload(), _uid())
        assert cov.id
        assert cov.status == "ACTIVE"
        assert cov.coverage_type == "HEALTH"

    async def test_get_coverage(self, db: AsyncSession, ins_service: InsuranceService):
        created = await ins_service.create_coverage(db, _cov_payload(), _uid())
        got = await ins_service.get_coverage(db, created.id)
        assert got is not None
        assert got.id == created.id

    async def test_list_coverages(self, db: AsyncSession, ins_service: InsuranceService):
        pid = _uid()
        await ins_service.create_coverage(db, _cov_payload(patient_id=pid), _uid())
        await ins_service.create_coverage(db, _cov_payload(patient_id=pid, coverage_type="DENTAL"), _uid())
        items = await ins_service.list_coverages(db, patient_id=pid)
        assert len(items) == 2

    async def test_update_coverage(self, db: AsyncSession, ins_service: InsuranceService):
        cov = await ins_service.create_coverage(db, _cov_payload(), _uid())
        updated = await ins_service.update_coverage(db, cov.id, CoverageUpdate(plan_name="Gold"), _uid())
        assert updated.plan_name == "Gold"
        assert updated.model_version == 2

    async def test_deactivate_coverage(self, db: AsyncSession, ins_service: InsuranceService):
        cov = await ins_service.create_coverage(db, _cov_payload(), _uid())
        await ins_service.update_coverage(db, cov.id, CoverageUpdate(is_active=False), _uid())
        items = await ins_service.list_coverages(db, active_only=True)
        assert len(items) == 0

    async def test_get_nonexistent_coverage(self, db: AsyncSession, ins_service: InsuranceService):
        assert await ins_service.get_coverage(db, _uid()) is None


# ── Claims ──────────────────────────────────────────────────────────────────────


class TestClaims:
    async def test_create_claim(self, db: AsyncSession, ins_service: InsuranceService):
        claim = await ins_service.create_claim(db, _claim_payload(), _uid())
        assert claim.id
        assert claim.status == "DRAFT"

    async def test_submit_claim(self, db: AsyncSession, ins_service: InsuranceService):
        claim = await ins_service.create_claim(db, _claim_payload(), _uid())
        submitted = await ins_service.submit_claim(db, claim.id, _uid())
        assert submitted.status == "SUBMITTED"
        assert submitted.submitted_at is not None

    async def test_submit_non_draft_claim_raises(self, db: AsyncSession, ins_service: InsuranceService):
        claim = await ins_service.create_claim(db, _claim_payload(), _uid())
        await ins_service.submit_claim(db, claim.id, _uid())
        with pytest.raises(InsuranceError, match="Only DRAFT"):
            await ins_service.submit_claim(db, claim.id, _uid())

    async def test_adjudicate_claim(self, db: AsyncSession, ins_service: InsuranceService):
        claim = await ins_service.create_claim(db, _claim_payload(), _uid())
        await ins_service.submit_claim(db, claim.id, _uid())
        adjudicated = await ins_service.adjudicate_claim(
            db, claim.id,
            ClaimUpdate(status="APPROVED", approved_amount=80.0, patient_responsibility=20.0),
            _uid(),
        )
        assert adjudicated.status == "APPROVED"
        assert adjudicated.approved_amount == 80.0
        assert adjudicated.adjudicated_at is not None

    async def test_adjudicate_non_submitted_raises(self, db: AsyncSession, ins_service: InsuranceService):
        claim = await ins_service.create_claim(db, _claim_payload(), _uid())
        with pytest.raises(InsuranceError, match="SUBMITTED/REVIEWING"):
            await ins_service.adjudicate_claim(db, claim.id, ClaimUpdate(status="APPROVED"), _uid())

    async def test_deny_claim(self, db: AsyncSession, ins_service: InsuranceService):
        claim = await ins_service.create_claim(db, _claim_payload(), _uid())
        await ins_service.submit_claim(db, claim.id, _uid())
        denied = await ins_service.adjudicate_claim(
            db, claim.id,
            ClaimUpdate(status="DENIED", denial_reason="Not covered"),
            _uid(),
        )
        assert denied.status == "DENIED"
        assert denied.denial_reason == "Not covered"

    async def test_list_claims(self, db: AsyncSession, ins_service: InsuranceService):
        cid = _uid()
        for _ in range(3):
            await ins_service.create_claim(db, _claim_payload(coverage_id=cid), _uid())
        items = await ins_service.list_claims(db, coverage_id=cid)
        assert len(items) == 3

    async def test_get_nonexistent_claim(self, db: AsyncSession, ins_service: InsuranceService):
        assert await ins_service.get_claim(db, _uid()) is None

    async def test_cannot_update_paid_claim(self, db: AsyncSession, ins_service: InsuranceService):
        claim = await ins_service.create_claim(db, _claim_payload(), _uid())
        await ins_service.submit_claim(db, claim.id, _uid())
        await ins_service.adjudicate_claim(db, claim.id, ClaimUpdate(status="PAID", paid_amount=80.0), _uid())
        with pytest.raises(InsuranceError, match="Cannot update"):
            await ins_service.update_claim(db, claim.id, ClaimUpdate(paid_amount=90.0), _uid())


# ── Prior Authorizations ────────────────────────────────────────────────────────


class TestPriorAuthorizations:
    async def test_create_prior_auth(self, db: AsyncSession, ins_service: InsuranceService):
        pauth = await ins_service.create_prior_auth(db, _pauth_payload(), _uid())
        assert pauth.id
        assert pauth.status == "PENDING"

    async def test_approve_prior_auth(self, db: AsyncSession, ins_service: InsuranceService):
        pauth = await ins_service.create_prior_auth(db, _pauth_payload(), _uid())
        approved = await ins_service.decide_prior_auth(
            db, pauth.id,
            PriorAuthDecision(decision="APPROVED", approved_units=3, valid_from="2025-06-01", valid_to="2025-12-31", decided_by=_uid()),
            _uid(),
        )
        assert approved.status == "APPROVED"
        assert approved.approved_units == 3
        assert approved.valid_from == "2025-06-01"

    async def test_deny_prior_auth(self, db: AsyncSession, ins_service: InsuranceService):
        pauth = await ins_service.create_prior_auth(db, _pauth_payload(), _uid())
        denied = await ins_service.decide_prior_auth(
            db, pauth.id,
            PriorAuthDecision(decision="DENIED", denial_reason="Not medically necessary", decided_by=_uid()),
            _uid(),
        )
        assert denied.status == "DENIED"
        assert denied.denial_reason == "Not medically necessary"

    async def test_decide_non_pending_raises(self, db: AsyncSession, ins_service: InsuranceService):
        pauth = await ins_service.create_prior_auth(db, _pauth_payload(), _uid())
        await ins_service.decide_prior_auth(db, pauth.id, PriorAuthDecision(decision="APPROVED", decided_by=_uid()), _uid())
        with pytest.raises(InsuranceError, match="Cannot decide"):
            await ins_service.decide_prior_auth(db, pauth.id, PriorAuthDecision(decision="DENIED", decided_by=_uid()), _uid())

    async def test_cancel_prior_auth(self, db: AsyncSession, ins_service: InsuranceService):
        pauth = await ins_service.create_prior_auth(db, _pauth_payload(), _uid())
        cancelled = await ins_service.cancel_prior_auth(db, pauth.id, _uid())
        assert cancelled.status == "CANCELLED"

    async def test_cancel_decided_prior_auth_raises(self, db: AsyncSession, ins_service: InsuranceService):
        pauth = await ins_service.create_prior_auth(db, _pauth_payload(), _uid())
        await ins_service.decide_prior_auth(db, pauth.id, PriorAuthDecision(decision="APPROVED", decided_by=_uid()), _uid())
        with pytest.raises(InsuranceError, match="Cannot cancel"):
            await ins_service.cancel_prior_auth(db, pauth.id, _uid())

    async def test_list_prior_auths(self, db: AsyncSession, ins_service: InsuranceService):
        pid = _uid()
        for _ in range(2):
            await ins_service.create_prior_auth(db, _pauth_payload(patient_id=pid), _uid())
        items = await ins_service.list_prior_auths(db, patient_id=pid)
        assert len(items) == 2

    async def test_get_nonexistent_prior_auth(self, db: AsyncSession, ins_service: InsuranceService):
        assert await ins_service.get_prior_auth(db, _uid()) is None
