"""Radiology service tests."""

import pytest

from radiology_service.dto.schemas import (
    ModalityCreate,
    ModalityUpdate,
    RadiologyOrderCreate,
    RadiologyOrderUpdate,
    RadiologyReportCreate,
    RadiologyReportUpdate,
    RadiologyReportSign,
    StudyCreate,
    StudyStart,
    StudyComplete,
)
from radiology_service.service.radiology_service import RadiologyError


async def _create_modality(session, svc, actor_id, code="CT", name="Computed Tomography"):
    payload = ModalityCreate(code=code, name=name, description=f"{name} scanner", is_active=True)
    return await svc.create_modality(session, payload, actor_id)


async def _create_order(session, svc, actor_id, patient_id, doctor_id, modality_code="CT", body_region="CHEST"):
    payload = RadiologyOrderCreate(
        patient_id=patient_id, ordering_doctor=doctor_id,
        modality_code=modality_code, body_region=body_region,
        clinical_indication="Chest pain", priority="ROUTINE", contrast=False,
    )
    return await svc.create_order(session, payload, actor_id)


class TestModalityCatalog:
    async def test_create_modality(self, session, svc, actor_id):
        m = await _create_modality(session, svc, actor_id)
        assert m.id
        assert m.code == "CT"
        assert m.status == "ACTIVE"

    async def test_duplicate_code_rejected(self, session, svc, actor_id):
        await _create_modality(session, svc, actor_id, "CT", "CT")
        with pytest.raises(RadiologyError, match="already exists"):
            await _create_modality(session, svc, actor_id, "CT", "Another CT")

    async def test_list_modalities(self, session, svc, actor_id):
        await _create_modality(session, svc, actor_id, "CT", "CT")
        await _create_modality(session, svc, actor_id, "MRI", "MRI")
        items = await svc.list_modalities(session)
        assert len(items) == 2

    async def test_update_modality(self, session, svc, actor_id):
        m = await _create_modality(session, svc, actor_id)
        updated = await svc.update_modality(session, m.id, ModalityUpdate(name="CT Scanner"), actor_id)
        assert updated.name == "CT Scanner"
        assert updated.version == 2

    async def test_deactivate_modality(self, session, svc, actor_id):
        m = await _create_modality(session, svc, actor_id)
        await svc.deactivate_modality(session, m.id, actor_id)
        items = await svc.list_modalities(session)
        assert len(items) == 0

    async def test_deactivate_nonexistent_raises(self, session, svc, actor_id):
        import uuid
        with pytest.raises(RadiologyError, match="not found"):
            await svc.deactivate_modality(session, uuid.uuid4(), actor_id)


class TestRadiologyOrders:
    async def test_create_order(self, session, svc, actor_id, patient_id, doctor_id):
        await _create_modality(session, svc, actor_id)
        order = await _create_order(session, svc, actor_id, patient_id, doctor_id)
        assert order.id
        assert order.patient_id == patient_id
        assert order.modality_code == "CT"
        assert order.body_region == "CHEST"
        assert order.status == "ORDERED"

    async def test_get_order(self, session, svc, actor_id, patient_id, doctor_id):
        await _create_modality(session, svc, actor_id)
        order = await _create_order(session, svc, actor_id, patient_id, doctor_id)
        fetched = await svc.get_order(session, order.id)
        assert fetched is not None
        assert fetched.id == order.id

    async def test_list_orders_by_patient(self, session, svc, actor_id, patient_id, doctor_id):
        await _create_modality(session, svc, actor_id)
        await _create_order(session, svc, actor_id, patient_id, doctor_id)
        items = await svc.list_orders(session, patient_id=patient_id)
        assert len(items) == 1

    async def test_update_order_priority(self, session, svc, actor_id, patient_id, doctor_id):
        await _create_modality(session, svc, actor_id)
        order = await _create_order(session, svc, actor_id, patient_id, doctor_id)
        updated = await svc.update_order(session, order.id, RadiologyOrderUpdate(priority="URGENT"), actor_id)
        assert updated.priority == "URGENT"
        assert updated.version == 2

    async def test_cancel_order(self, session, svc, actor_id, patient_id, doctor_id):
        await _create_modality(session, svc, actor_id)
        order = await _create_order(session, svc, actor_id, patient_id, doctor_id)
        cancelled = await svc.cancel_order(session, order.id, actor_id)
        assert cancelled.status == "CANCELLED"

    async def test_cancel_completed_order_rejected(self, session, svc, actor_id, patient_id, doctor_id):
        await _create_modality(session, svc, actor_id)
        order = await _create_order(session, svc, actor_id, patient_id, doctor_id)
        await svc.cancel_order(session, order.id, actor_id)
        with pytest.raises(RadiologyError, match="Cannot cancel"):
            await svc.cancel_order(session, order.id, actor_id)


class TestStudies:
    async def _setup_order(self, session, svc, actor_id, patient_id, doctor_id):
        await _create_modality(session, svc, actor_id)
        return await _create_order(session, svc, actor_id, patient_id, doctor_id)

    async def test_create_study(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        payload = StudyCreate(
            order_id=order.id, patient_id=patient_id,
            modality_code="CT", body_region="CHEST",
            study_instance_uid="1.2.3.4", accession_number="ACC001",
        )
        study = await svc.create_study(session, payload, actor_id)
        assert study.id
        assert study.status == "SCHEDULED"
        assert study.study_instance_uid == "1.2.3.4"

    async def test_order_status_advances_to_scheduled(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        await svc.create_study(session, StudyCreate(order_id=order.id, patient_id=patient_id, modality_code="CT", body_region="CHEST"), actor_id)
        refreshed = await svc.get_order(session, order.id)
        assert refreshed.status == "SCHEDULED"

    async def test_duplicate_study_rejected(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        await svc.create_study(session, StudyCreate(order_id=order.id, patient_id=patient_id, modality_code="CT", body_region="CHEST"), actor_id)
        with pytest.raises(RadiologyError, match="Study already exists"):
            await svc.create_study(session, StudyCreate(order_id=order.id, patient_id=patient_id, modality_code="CT", body_region="CHEST"), actor_id)

    async def test_start_study(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        study = await svc.create_study(session, StudyCreate(order_id=order.id, patient_id=patient_id, modality_code="CT", body_region="CHEST"), actor_id)
        started = await svc.start_study(session, study.id, StudyStart(performed_by=doctor_id), actor_id)
        assert started.status == "IN_PROGRESS"
        assert started.performed_by == doctor_id
        assert started.started_at is not None

    async def test_complete_study(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        study = await svc.create_study(session, StudyCreate(order_id=order.id, patient_id=patient_id, modality_code="CT", body_region="CHEST"), actor_id)
        await svc.start_study(session, study.id, StudyStart(performed_by=doctor_id), actor_id)
        completed = await svc.complete_study(session, study.id, StudyComplete(technician_notes="No issues"), actor_id)
        assert completed.status == "COMPLETED"
        assert completed.completed_at is not None
        assert completed.technician_notes == "No issues"

    async def test_order_status_advances_through_workflow(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        study = await svc.create_study(session, StudyCreate(order_id=order.id, patient_id=patient_id, modality_code="CT", body_region="CHEST"), actor_id)
        await svc.start_study(session, study.id, StudyStart(performed_by=doctor_id), actor_id)
        refreshed = await svc.get_order(session, order.id)
        assert refreshed.status == "PERFORMING"
        await svc.complete_study(session, study.id, StudyComplete(), actor_id)
        refreshed = await svc.get_order(session, order.id)
        assert refreshed.status == "COMPLETED"

    async def test_start_nonexistent_study(self, session, svc, actor_id):
        import uuid
        with pytest.raises(RadiologyError, match="not found"):
            await svc.start_study(session, uuid.uuid4(), StudyStart(performed_by=uuid.uuid4()), actor_id)


class TestRadiologyReports:
    async def _setup_order(self, session, svc, actor_id, patient_id, doctor_id):
        await _create_modality(session, svc, actor_id)
        return await _create_order(session, svc, actor_id, patient_id, doctor_id)

    async def test_create_report(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        payload = RadiologyReportCreate(
            order_id=order.id, patient_id=patient_id,
            findings="No acute findings", impression="Normal chest X-ray",
            recommendation="Follow up in 6 months",
        )
        report = await svc.create_report(session, payload, actor_id)
        assert report.id
        assert report.status == "DRAFT"
        assert report.findings == "No acute findings"

    async def test_update_report(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        report = await svc.create_report(session, RadiologyReportCreate(order_id=order.id, patient_id=patient_id), actor_id)
        updated = await svc.update_report(session, report.id, RadiologyReportUpdate(findings="Mild opacity in right lower lobe"), actor_id)
        assert updated.findings == "Mild opacity in right lower lobe"
        assert updated.version == 2

    async def test_sign_report(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        report = await svc.create_report(session, RadiologyReportCreate(order_id=order.id, patient_id=patient_id, findings="Normal"), actor_id)
        signed = await svc.sign_report(session, report.id, RadiologyReportSign(signed_by=doctor_id), actor_id)
        assert signed.status == "FINAL"
        assert signed.signed_by == doctor_id
        assert signed.signed_at is not None

    async def test_update_final_report_rejected(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        report = await svc.create_report(session, RadiologyReportCreate(order_id=order.id, patient_id=patient_id), actor_id)
        await svc.sign_report(session, report.id, RadiologyReportSign(signed_by=doctor_id), actor_id)
        with pytest.raises(RadiologyError, match="Cannot update signed report"):
            await svc.update_report(session, report.id, RadiologyReportUpdate(findings="Changed"), actor_id)

    async def test_cancel_report(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        report = await svc.create_report(session, RadiologyReportCreate(order_id=order.id, patient_id=patient_id), actor_id)
        cancelled = await svc.cancel_report(session, report.id, actor_id)
        assert cancelled.status == "CANCELLED"

    async def test_list_reports(self, session, svc, actor_id, patient_id, doctor_id):
        order = await self._setup_order(session, svc, actor_id, patient_id, doctor_id)
        await svc.create_report(session, RadiologyReportCreate(order_id=order.id, patient_id=patient_id), actor_id)
        items = await svc.list_reports(session, patient_id=patient_id)
        assert len(items) == 1
