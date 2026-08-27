from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from ehos_common.events import DomainEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from laboratory_service.dto.schemas import (
    LabOrderCreate,
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
from laboratory_service.entity.models import LabOrder, LabOrderItem, LabResult, LabTest, Sample

TOPICS = {
    "TestCreated": "clinical.laboratory.test.created",
    "TestUpdated": "clinical.laboratory.test.updated",
    "OrderCreated": "clinical.laboratory.order.created",
    "OrderUpdated": "clinical.laboratory.order.updated",
    "ResultCreated": "clinical.laboratory.result.created",
    "ResultUpdated": "clinical.laboratory.result.updated",
    "ResultVerified": "clinical.laboratory.result.verified",
}


class LaboratoryError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class LaboratoryService:
    """Laboratory service: test catalog, orders, samples, results."""

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
                source="laboratory-service",
                user_id=None,
                payload={"occurredAt": datetime.now(UTC).isoformat(), **payload},
            )
            outbox = session.info.get("outbox")
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await self.producer.publish(topic, event)
        except Exception:
            pass  # publishing must never break the operation

    # ------------------------ LabTest catalog ------------------------

    async def create_test(self, session: AsyncSession, payload: LabTestCreate, actor_id: UUID) -> LabTest:
        existing = await session.execute(
            select(LabTest).where(LabTest.code == payload.code, LabTest.deleted_at.is_(None))
        )
        if existing.scalars().first():
            raise LaboratoryError("DUPLICATE_TEST", f"Test code '{payload.code}' already exists")

        test = LabTest(
            code=payload.code,
            name=payload.name,
            category=payload.category,
            unit=payload.unit,
            reference_low=payload.reference_low,
            reference_high=payload.reference_high,
            specimen_type=payload.specimen_type,
            turnaround_min=payload.turnaround_min,
            is_active=payload.is_active,
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(test)
        await session.flush()
        await self._publish(
            session,
            "TestCreated",
            {"code": test.code, "name": test.name, "category": test.category},
        )
        return test

    async def get_test(self, session: AsyncSession, test_id: UUID) -> LabTest | None:
        return await session.get(LabTest, test_id)

    async def list_tests(
        self, session: AsyncSession, category: str | None = None, active_only: bool = True, limit: int = 50, offset: int = 0
    ) -> list[LabTest]:
        stmt = select(LabTest).where(LabTest.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(LabTest.is_active.is_(True))
        if category:
            stmt = stmt.where(LabTest.category == category)
        stmt = stmt.order_by(LabTest.category, LabTest.name).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_test(self, session: AsyncSession, test_id: UUID, payload: LabTestUpdate, actor_id: UUID) -> LabTest:
        test = await self.get_test(session, test_id)
        if not test:
            raise LaboratoryError("TEST_NOT_FOUND", "Test not found")

        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(test, k, v)
        test.updated_by = actor_id
        test.version += 1

        await self._publish(
            session,
            "TestUpdated",
            {"test_id": str(test.id), **data},
        )
        return test

    async def deactivate_test(self, session: AsyncSession, test_id: UUID, actor_id: UUID) -> LabTest:
        test = await self.get_test(session, test_id)
        if not test:
            raise LaboratoryError("TEST_NOT_FOUND", "Test not found")
        test.is_active = False
        test.deleted_at = datetime.utcnow()
        test.deleted_by = actor_id
        test.deletion_reason = "deactivated"
        test.updated_by = actor_id
        test.version += 1
        return test

    # ------------------------ LabOrder ------------------------

    async def create_order(self, session: AsyncSession, payload: LabOrderCreate, actor_id: UUID) -> LabOrder:
        # Snapshot patient demographics (would fetch from patient-service in real impl)
        patient_snapshot = {"patient_id": str(payload.patient_id), "snapshot_at": datetime.utcnow().isoformat()}

        order = LabOrder(
            patient_id=payload.patient_id,
            patient_snapshot=patient_snapshot,
            encounter_id=payload.encounter_id,
            ordering_doctor=payload.ordering_doctor,
            priority=payload.priority,
            clinical_notes=payload.clinical_notes,
            status="ORDERED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(order)
        await session.flush()

        items = []
        for item_payload in payload.items:
            test_name = item_payload.test_name
            if item_payload.test_id:
                test = await self.get_test(session, item_payload.test_id)
                if test:
                    test_name = test.name
            item = LabOrderItem(
                lab_order_id=order.id,
                test_id=item_payload.test_id,
                test_name=test_name,
                specimen_type=item_payload.specimen_type,
                status="ORDERED",
                created_by=actor_id,
                updated_by=actor_id,
            )
            session.add(item)
            items.append(item)

        await session.flush()

        await self._publish(
            session,
            "OrderCreated",
            {"patient_id": str(order.patient_id), "priority": order.priority, "item_count": len(items)},
        )
        return order

    async def get_order(self, session: AsyncSession, order_id: UUID) -> LabOrder | None:
        result = await session.execute(
            select(LabOrder)
            .where(LabOrder.id == order_id, LabOrder.deleted_at.is_(None))
            .options(selectinload(LabOrder.items), selectinload(LabOrder.samples))
        )
        return result.scalars().first()

    async def list_orders(
        self,
        session: AsyncSession,
        patient_id: UUID | None = None,
        ordering_doctor: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LabOrder]:
        stmt = select(LabOrder).where(LabOrder.deleted_at.is_(None))
        if patient_id:
            stmt = stmt.where(LabOrder.patient_id == patient_id)
        if ordering_doctor:
            stmt = stmt.where(LabOrder.ordering_doctor == ordering_doctor)
        if status:
            stmt = stmt.where(LabOrder.status == status)
        stmt = stmt.order_by(LabOrder.ordered_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_order(self, session: AsyncSession, order_id: UUID, payload: LabOrderUpdate, actor_id: UUID) -> LabOrder:
        order = await self.get_order(session, order_id)
        if not order:
            raise LaboratoryError("ORDER_NOT_FOUND", "Order not found")

        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(order, k, v)
        order.updated_by = actor_id
        order.version += 1

        await self._publish(
            session,
            "OrderUpdated",
            {"order_id": str(order.id), **data},
        )
        return order

    async def cancel_order(self, session: AsyncSession, order_id: UUID, actor_id: UUID) -> LabOrder:
        order = await self.get_order(session, order_id)
        if not order:
            raise LaboratoryError("ORDER_NOT_FOUND", "Order not found")
        if order.status in ("VERIFIED", "CANCELLED"):
            raise LaboratoryError("INVALID_STATE", f"Cannot cancel order in status {order.status}")
        order.status = "CANCELLED"
        order.updated_by = actor_id
        order.version += 1

        # Cancel pending items and samples
        for item in order.items:
            if item.status != "RESULTED":
                item.status = "CANCELLED"
        for sample in order.samples:
            if sample.status not in ("ANALYZED", "DISCARDED"):
                sample.status = "DISCARDED"

        return order

    # ------------------------ Samples ------------------------

    async def create_sample(self, session: AsyncSession, payload: SampleCreate, actor_id: UUID) -> Sample:
        # Verify order exists
        order = await self.get_order(session, payload.lab_order_id)
        if not order:
            raise LaboratoryError("ORDER_NOT_FOUND", "Lab order not found")

        # Check barcode uniqueness
        existing = await session.execute(
            select(Sample).where(Sample.barcode == payload.barcode, Sample.deleted_at.is_(None))
        )
        if existing.scalars().first():
            raise LaboratoryError("DUPLICATE_BARCODE", f"Barcode '{payload.barcode}' already exists")

        sample = Sample(
            lab_order_id=payload.lab_order_id,
            patient_id=payload.patient_id,
            barcode=payload.barcode,
            sample_type=payload.sample_type,
            status="REQUESTED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(sample)
        await session.flush()

        # Update order status if needed
        if order.status == "ORDERED":
            order.status = "COLLECTED"
            order.updated_by = actor_id
            order.version += 1

        return sample

    async def collect_sample(self, session: AsyncSession, sample_id: UUID, payload: SampleCollect, actor_id: UUID) -> Sample:
        sample = await session.get(Sample, sample_id)
        if not sample:
            raise LaboratoryError("SAMPLE_NOT_FOUND", "Sample not found")
        if sample.status != "REQUESTED":
            raise LaboratoryError("INVALID_STATE", f"Cannot collect sample in status {sample.status}")

        sample.status = "COLLECTED"
        sample.collected_by = payload.collected_by
        sample.collection_time = payload.collection_time or datetime.utcnow()
        sample.updated_by = actor_id
        sample.version += 1
        return sample

    async def receive_sample(self, session: AsyncSession, sample_id: UUID, payload: SampleReceive, actor_id: UUID) -> Sample:
        sample = await session.get(Sample, sample_id)
        if not sample:
            raise LaboratoryError("SAMPLE_NOT_FOUND", "Sample not found")
        if sample.status not in ("COLLECTED", "IN_TRANSIT"):
            raise LaboratoryError("INVALID_STATE", f"Cannot receive sample in status {sample.status}")

        sample.status = "RECEIVED"
        sample.received_by = payload.received_by
        sample.received_at = payload.received_at or datetime.utcnow()
        sample.updated_by = actor_id
        sample.version += 1

        # Update order status
        order = await self.get_order(session, sample.lab_order_id)
        if order and order.status == "COLLECTED":
            order.status = "IN_PROGRESS"
            order.updated_by = actor_id
            order.version += 1

        return sample

    async def reject_sample(self, session: AsyncSession, sample_id: UUID, payload: SampleReject, actor_id: UUID) -> Sample:
        sample = await session.get(Sample, sample_id)
        if not sample:
            raise LaboratoryError("SAMPLE_NOT_FOUND", "Sample not found")
        if sample.status in ("ANALYZED", "DISCARDED"):
            raise LaboratoryError("INVALID_STATE", f"Cannot reject sample in status {sample.status}")

        sample.status = "REJECTED"
        sample.rejection_reason = payload.rejection_reason
        sample.updated_by = actor_id
        sample.version += 1
        return sample

    # ------------------------ LabResults ------------------------

    def _compute_flag(self, test: LabTest | None, value: Decimal | None) -> str | None:
        if value is None or test is None or test.reference_low is None or test.reference_high is None:
            return None
        if value < test.reference_low:
            return "LOW"
        if value > test.reference_high:
            return "HIGH"
        return "NORMAL"

    async def create_result(self, session: AsyncSession, payload: LabResultCreate, actor_id: UUID) -> LabResult:
        # Verify order item
        item = await session.get(LabOrderItem, payload.order_item_id)
        if not item:
            raise LaboratoryError("ORDER_ITEM_NOT_FOUND", "Order item not found")

        # Verify sample if provided
        if payload.sample_id:
            sample = await session.get(Sample, payload.sample_id)
            if not sample:
                raise LaboratoryError("SAMPLE_NOT_FOUND", "Sample not found")

        # Get test for flag computation
        test = None
        if payload.test_id:
            test = await self.get_test(session, payload.test_id)

        flag = payload.flag or self._compute_flag(test, payload.result_numeric)

        result = LabResult(
            order_item_id=payload.order_item_id,
            sample_id=payload.sample_id,
            patient_id=payload.patient_id,
            test_id=payload.test_id,
            test_name=payload.test_name,
            result_numeric=payload.result_numeric,
            result_text=payload.result_text,
            unit=payload.unit,
            reference_range=payload.reference_range,
            flag=flag,
            performed_by=payload.performed_by or actor_id,
            performed_at=payload.performed_at or datetime.utcnow(),
            status=payload.status,
            instrumentation=payload.instrumentation,
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(result)
        await session.flush()

        # Update item status
        if payload.status in ("PRELIMINARY", "VERIFIED", "AMENDED"):
            item.status = "RESULTED"

        await self._publish(
            session,
            "ResultCreated",
            {
                "patient_id": str(result.patient_id),
                "test_name": result.test_name,
                "flag": result.flag,
                "status": result.status,
            },
        )
        return result

    async def get_result(self, session: AsyncSession, result_id: UUID) -> LabResult | None:
        return await session.get(LabResult, result_id)

    async def list_results(
        self,
        session: AsyncSession,
        patient_id: UUID | None = None,
        order_item_id: UUID | None = None,
        test_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LabResult]:
        stmt = select(LabResult).where(LabResult.deleted_at.is_(None))
        if patient_id:
            stmt = stmt.where(LabResult.patient_id == patient_id)
        if order_item_id:
            stmt = stmt.where(LabResult.order_item_id == order_item_id)
        if test_id:
            stmt = stmt.where(LabResult.test_id == test_id)
        if status:
            stmt = stmt.where(LabResult.status == status)
        stmt = stmt.order_by(LabResult.performed_at.desc().nullslast()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_result(self, session: AsyncSession, result_id: UUID, payload: LabResultUpdate, actor_id: UUID) -> LabResult:
        result = await self.get_result(session, result_id)
        if not result:
            raise LaboratoryError("RESULT_NOT_FOUND", "Result not found")
        if result.status == "CANCELLED":
            raise LaboratoryError("INVALID_STATE", "Cannot update cancelled result")

        test = None
        if result.test_id:
            test = await self.get_test(session, result.test_id)

        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(result, k, v)

        # Recompute flag if numeric result changed
        if "result_numeric" in data:
            result.flag = self._compute_flag(test, result.result_numeric)

        result.updated_by = actor_id
        result.version += 1

        await self._publish(
            session,
            "ResultUpdated",
            {"result_id": str(result.id), **data},
        )
        return result

    async def verify_result(self, session: AsyncSession, result_id: UUID, payload: LabResultVerify, actor_id: UUID) -> LabResult:
        result = await self.get_result(session, result_id)
        if not result:
            raise LaboratoryError("RESULT_NOT_FOUND", "Result not found")
        if result.status == "CANCELLED":
            raise LaboratoryError("INVALID_STATE", "Cannot verify cancelled result")

        result.status = "VERIFIED"
        result.verified_by = payload.verified_by
        result.verified_at = payload.verified_at or datetime.utcnow()
        result.updated_by = actor_id
        result.version += 1

        # Check if all items in order are resulted/verified
        item = await session.get(LabOrderItem, result.order_item_id)
        if item:
            order = await self.get_order(session, item.lab_order_id)
            if order:
                all_items_resulted = all(i.status in ("RESULTED", "CANCELLED") for i in order.items)
                if all_items_resulted:
                    order.status = "VERIFIED"
                    order.updated_by = actor_id
                    order.version += 1

        await self._publish(
            session,
            "ResultVerified",
            {"result_id": str(result.id), "verified_by": str(payload.verified_by)},
        )
        return result

    async def cancel_result(self, session: AsyncSession, result_id: UUID, actor_id: UUID) -> LabResult:
        result = await self.get_result(session, result_id)
        if not result:
            raise LaboratoryError("RESULT_NOT_FOUND", "Result not found")
        result.status = "CANCELLED"
        result.updated_by = actor_id
        result.version += 1
        return result


service = LaboratoryService()
