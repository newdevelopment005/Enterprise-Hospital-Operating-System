"""Laboratory service tests."""

from uuid import uuid4

import pytest

from laboratory_service.dto.schemas import (
    LabOrderCreate,
    LabOrderItemCreate,
    LabOrderUpdate,
    LabResultCreate,
    LabResultUpdate,
    LabResultVerify,
    LabTestCreate,
    LabTestUpdate,
    SampleCollect,
    SampleCreate,
    SampleReceive,
    SampleReject,
)
from laboratory_service.service.laboratory_service import LaboratoryError


async def _create_test(session, service, actor_id, code="CBC", name="Complete Blood Count", category="HEMATOLOGY", reference_low=None, reference_high=None):
    payload = LabTestCreate(code=code, name=name, category=category, reference_low=reference_low, reference_high=reference_high)
    return await service.create_test(session, payload, actor_id)


async def _create_order(session, service, actor_id, patient_id, doctor_id, test_id=None):
    items = [LabOrderItemCreate(test_id=test_id, test_name="CBC", specimen_type="BLOOD")]
    payload = LabOrderCreate(patient_id=patient_id, ordering_doctor=doctor_id, priority="ROUTINE", items=items)
    order = await service.create_order(session, payload, actor_id)
    # Re-query with items loaded
    return await service.get_order(session, order.id)


class TestLabTestCatalog:
    async def test_create_test(self, session, service, actor_id):
        test = await _create_test(session, service, actor_id)
        assert test.id
        assert test.code == "CBC"
        assert test.status == "ACTIVE"

    async def test_duplicate_code_rejected(self, session, service, actor_id):
        await _create_test(session, service, actor_id, "CBC", "CBC")
        with pytest.raises(LaboratoryError, match="already exists"):
            await _create_test(session, service, actor_id, "CBC", "Another CBC")

    async def test_list_tests_filter_category(self, session, service, actor_id):
        await _create_test(session, service, actor_id, "CBC", "CBC", "HEMATOLOGY")
        await _create_test(session, service, actor_id, "GLU", "Glucose", "CHEMISTRY")
        hema = await service.list_tests(session, category="HEMATOLOGY")
        assert len(hema) == 1
        assert hema[0].code == "CBC"

    async def test_update_test(self, session, service, actor_id):
        test = await _create_test(session, service, actor_id)
        updated = await service.update_test(session, test.id, LabTestUpdate(name="CBC with Diff"), actor_id)
        assert updated.name == "CBC with Diff"
        assert updated.version == 2

    async def test_deactivate_test(self, session, service, actor_id):
        test = await _create_test(session, service, actor_id)
        await service.deactivate_test(session, test.id, actor_id)
        assert test.is_active is False
        assert test.deleted_at is not None


class TestLabOrders:
    async def test_create_order(self, session, service, actor_id, patient_id, doctor_id):
        test = await _create_test(session, service, actor_id)
        order = await _create_order(session, service, actor_id, patient_id, doctor_id, test.id)
        assert order.id
        assert order.status == "ORDERED"
        # Re-query with items loaded
        order = await service.get_order(session, order.id)
        assert len(order.items) == 1
        assert order.items[0].test_name == "Complete Blood Count"

    async def test_create_order_without_catalog_test(self, session, service, actor_id, patient_id, doctor_id):
        items = [LabOrderItemCreate(test_id=None, test_name="Custom Test", specimen_type="URINE")]
        payload = LabOrderCreate(patient_id=patient_id, ordering_doctor=doctor_id, priority="URGENT", items=items)
        order = await service.create_order(session, payload, actor_id)
        order = await service.get_order(session, order.id)
        assert order.items[0].test_id is None
        assert order.items[0].test_name == "Custom Test"

    async def test_list_orders_by_patient(self, session, service, actor_id, patient_id, doctor_id):
        await _create_order(session, service, actor_id, patient_id, doctor_id)
        other_patient = uuid4()
        await _create_order(session, service, actor_id, other_patient, doctor_id)
        orders = await service.list_orders(session, patient_id=patient_id)
        assert len(orders) == 1

    async def test_update_order_priority(self, session, service, actor_id, patient_id, doctor_id):
        order = await _create_order(session, service, actor_id, patient_id, doctor_id)
        updated = await service.update_order(session, order.id, LabOrderUpdate(priority="STAT"), actor_id)
        assert updated.priority == "STAT"
        assert updated.version == 2

    async def test_cancel_order(self, session, service, actor_id, patient_id, doctor_id):
        order = await _create_order(session, service, actor_id, patient_id, doctor_id)
        cancelled = await service.cancel_order(session, order.id, actor_id)
        assert cancelled.status == "CANCELLED"


class TestSamples:
    async def test_create_sample(self, session, service, actor_id, patient_id, doctor_id):
        order = await _create_order(session, service, actor_id, patient_id, doctor_id)
        payload = SampleCreate(lab_order_id=order.id, patient_id=patient_id, barcode="SMP-001", sample_type="BLOOD")
        sample = await service.create_sample(session, payload, actor_id)
        assert sample.id
        assert sample.status == "REQUESTED"

    async def test_duplicate_barcode_rejected(self, session, service, actor_id, patient_id, doctor_id):
        order = await _create_order(session, service, actor_id, patient_id, doctor_id)
        await service.create_sample(session, SampleCreate(lab_order_id=order.id, patient_id=patient_id, barcode="SMP-001", sample_type="BLOOD"), actor_id)
        with pytest.raises(LaboratoryError, match="already exists"):
            await service.create_sample(session, SampleCreate(lab_order_id=order.id, patient_id=patient_id, barcode="SMP-001", sample_type="URINE"), actor_id)

    async def test_sample_lifecycle(self, session, service, actor_id, patient_id, doctor_id):
        order = await _create_order(session, service, actor_id, patient_id, doctor_id)
        sample = await service.create_sample(session, SampleCreate(lab_order_id=order.id, patient_id=patient_id, barcode="SMP-002", sample_type="BLOOD"), actor_id)

        # collect
        collected = await service.collect_sample(session, sample.id, SampleCollect(collected_by=doctor_id), actor_id)
        assert collected.status == "COLLECTED"
        assert collected.collected_by == doctor_id

        # receive
        received = await service.receive_sample(session, sample.id, SampleReceive(received_by=actor_id), actor_id)
        assert received.status == "RECEIVED"
        assert received.received_by == actor_id

        # order status should be IN_PROGRESS
        refreshed_order = await service.get_order(session, order.id)
        assert refreshed_order.status == "IN_PROGRESS"

    async def test_reject_sample(self, session, service, actor_id, patient_id, doctor_id):
        order = await _create_order(session, service, actor_id, patient_id, doctor_id)
        sample = await service.create_sample(session, SampleCreate(lab_order_id=order.id, patient_id=patient_id, barcode="SMP-003", sample_type="BLOOD"), actor_id)
        await service.collect_sample(session, sample.id, SampleCollect(collected_by=doctor_id), actor_id)
        rejected = await service.reject_sample(session, sample.id, SampleReject(rejection_reason="Hemolyzed"), actor_id)
        assert rejected.status == "REJECTED"
        assert rejected.rejection_reason == "Hemolyzed"


class TestLabResults:
    async def test_create_result(self, session, service, actor_id, patient_id, doctor_id):
        test = await _create_test(session, service, actor_id, "GLU", "Glucose", "CHEMISTRY", reference_low=70, reference_high=110)
        order = await _create_order(session, service, actor_id, patient_id, doctor_id, test.id)
        payload = LabResultCreate(
            order_item_id=order.items[0].id,
            patient_id=patient_id,
            test_id=test.id,
            test_name="Glucose",
            result_numeric=120,
            unit="mg/dL",
            reference_range="70-110",
            status="PRELIMINARY",
        )
        result = await service.create_result(session, payload, actor_id)
        assert result.id
        assert result.result_numeric == 120
        assert result.flag == "HIGH"  # auto-computed
        assert result.status == "PRELIMINARY"
        # item status should be RESULTED
        item = await service.get_order(session, order.id)
        assert item.items[0].status == "RESULTED"

    async def test_create_result_with_text(self, session, service, actor_id, patient_id, doctor_id):
        test = await _create_test(session, service, actor_id, "CULT", "Blood Culture", "MICROBIOLOGY")
        order = await _create_order(session, service, actor_id, patient_id, doctor_id, test.id)
        payload = LabResultCreate(
            order_item_id=order.items[0].id,
            patient_id=patient_id,
            test_id=test.id,
            test_name="Blood Culture",
            result_text="No growth after 48h",
            status="VERIFIED",
        )
        result = await service.create_result(session, payload, actor_id)
        assert result.result_text == "No growth after 48h"
        assert result.flag is None  # no numeric

    async def test_verify_result(self, session, service, actor_id, patient_id, doctor_id):
        test = await _create_test(session, service, actor_id, "K", "Potassium", "CHEMISTRY", reference_low=3.5, reference_high=5.0)
        order = await _create_order(session, service, actor_id, patient_id, doctor_id, test.id)
        result = await service.create_result(
            session,
            LabResultCreate(
                order_item_id=order.items[0].id,
                patient_id=patient_id,
                test_id=test.id,
                test_name="Potassium",
                result_numeric=4.2,
                unit="mmol/L",
                reference_range="3.5-5.0",
                status="PRELIMINARY",
            ),
            actor_id,
        )
        verified = await service.verify_result(session, result.id, LabResultVerify(verified_by=doctor_id), actor_id)
        assert verified.status == "VERIFIED"
        assert verified.verified_by == doctor_id

    async def test_update_result(self, session, service, actor_id, patient_id, doctor_id):
        test = await _create_test(session, service, actor_id, "NA", "Sodium", "CHEMISTRY", reference_low=135, reference_high=145)
        order = await _create_order(session, service, actor_id, patient_id, doctor_id, test.id)
        result = await service.create_result(
            session,
            LabResultCreate(
                order_item_id=order.items[0].id,
                patient_id=patient_id,
                test_id=test.id,
                test_name="Sodium",
                result_numeric=150,
                unit="mmol/L",
                reference_range="135-145",
                status="PRELIMINARY",
            ),
            actor_id,
        )
        assert result.flag == "HIGH"
        updated = await service.update_result(session, result.id, LabResultUpdate(result_numeric=140), actor_id)
        assert updated.result_numeric == 140
        assert updated.flag == "NORMAL"  # recomputed

    async def test_list_results_by_patient(self, session, service, actor_id, patient_id, doctor_id):
        test = await _create_test(session, service, actor_id, "CBC", "CBC", "HEMATOLOGY")
        order = await _create_order(session, service, actor_id, patient_id, doctor_id, test.id)
        await service.create_result(
            session,
            LabResultCreate(
                order_item_id=order.items[0].id,
                patient_id=patient_id,
                test_id=test.id,
                test_name="CBC",
                result_numeric=5000,
                unit="/uL",
                status="PRELIMINARY",
            ),
            actor_id,
        )
        other_patient = uuid4()
        order2 = await _create_order(session, service, actor_id, other_patient, doctor_id, test.id)
        await service.create_result(
            session,
            LabResultCreate(
                order_item_id=order2.items[0].id,
                patient_id=other_patient,
                test_id=test.id,
                test_name="CBC",
                result_numeric=6000,
                unit="/uL",
                status="PRELIMINARY",
            ),
            actor_id,
        )
        results = await service.list_results(session, patient_id=patient_id)
        assert len(results) == 1

    async def test_cancel_result(self, session, service, actor_id, patient_id, doctor_id):
        test = await _create_test(session, service, actor_id)
        order = await _create_order(session, service, actor_id, patient_id, doctor_id, test.id)
        result = await service.create_result(
            session,
            LabResultCreate(
                order_item_id=order.items[0].id,
                patient_id=patient_id,
                test_id=test.id,
                test_name="Test",
                status="PRELIMINARY",
            ),
            actor_id,
        )
        cancelled = await service.cancel_result(session, result.id, actor_id)
        assert cancelled.status == "CANCELLED"
