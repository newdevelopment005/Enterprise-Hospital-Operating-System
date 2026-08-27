from datetime import UTC, datetime
from uuid import UUID

from ehos_common.events import DomainEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from radiology_service.dto.schemas import (
    ModalityCreate,
    ModalityUpdate,
    RadiologyOrderCreate,
    RadiologyOrderUpdate,
    RadiologyReportCreate,
    RadiologyReportUpdate,
    RadiologyReportSign,
    StudyComplete,
    StudyCreate,
    StudyStart,
)
from radiology_service.entity.models import Modality, RadiologyOrder, RadiologyReport, Study

TOPICS = {
    "ModalityCreated": "clinical.radiology.modality.created",
    "ModalityUpdated": "clinical.radiology.modality.updated",
    "OrderCreated": "clinical.radiology.order.created",
    "OrderUpdated": "clinical.radiology.order.updated",
    "StudyCreated": "clinical.radiology.study.created",
    "StudyUpdated": "clinical.radiology.study.updated",
    "ReportCreated": "clinical.radiology.report.created",
    "ReportUpdated": "clinical.radiology.report.updated",
    "ReportSigned": "clinical.radiology.report.signed",
}


class RadiologyError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class RadiologyService:
    """Radiology service: modality catalog, orders, studies, reports."""

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
                source="radiology-service",
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

    # ------------------------ Modality catalog ------------------------

    async def create_modality(self, session: AsyncSession, payload: ModalityCreate, actor_id: UUID) -> Modality:
        existing = await session.execute(select(Modality).where(Modality.code == payload.code, Modality.deleted_at.is_(None)))
        if existing.scalars().first():
            raise RadiologyError("DUPLICATE_MODALITY", f"Modality code '{payload.code}' already exists")

        modality = Modality(
            code=payload.code,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(modality)
        await session.flush()
        await self._publish(session, "ModalityCreated", {"code": modality.code, "name": modality.name})
        return modality

    async def get_modality(self, session: AsyncSession, modality_id: UUID) -> Modality | None:
        return await session.get(Modality, modality_id)

    async def list_modalities(self, session: AsyncSession, active_only: bool = True, limit: int = 50, offset: int = 0) -> list[Modality]:
        stmt = select(Modality).where(Modality.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(Modality.is_active.is_(True))
        stmt = stmt.order_by(Modality.name).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_modality(self, session: AsyncSession, modality_id: UUID, payload: ModalityUpdate, actor_id: UUID) -> Modality:
        modality = await self.get_modality(session, modality_id)
        if not modality:
            raise RadiologyError("MODALITY_NOT_FOUND", "Modality not found")

        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(modality, k, v)
        modality.updated_by = actor_id
        modality.version += 1
        await self._publish(session, "ModalityUpdated", {"modality_id": str(modality.id), **data})
        return modality

    async def deactivate_modality(self, session: AsyncSession, modality_id: UUID, actor_id: UUID) -> Modality:
        modality = await self.get_modality(session, modality_id)
        if not modality:
            raise RadiologyError("MODALITY_NOT_FOUND", "Modality not found")
        modality.is_active = False
        modality.deleted_at = datetime.utcnow()
        modality.deleted_by = actor_id
        modality.deletion_reason = "deactivated"
        modality.updated_by = actor_id
        modality.version += 1
        return modality

    # ------------------------ RadiologyOrder ------------------------

    async def create_order(self, session: AsyncSession, payload: RadiologyOrderCreate, actor_id: UUID) -> RadiologyOrder:
        patient_snapshot = {"patient_id": str(payload.patient_id), "snapshot_at": datetime.utcnow().isoformat()}

        order = RadiologyOrder(
            patient_id=payload.patient_id,
            patient_snapshot=patient_snapshot,
            encounter_id=payload.encounter_id,
            ordering_doctor=payload.ordering_doctor,
            modality_code=payload.modality_code,
            body_region=payload.body_region,
            clinical_indication=payload.clinical_indication,
            priority=payload.priority,
            contrast=payload.contrast,
            status="ORDERED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(order)
        await session.flush()

        await self._publish(
            session,
            "OrderCreated",
            {"patient_id": str(order.patient_id), "modality": order.modality_code, "body_region": order.body_region},
        )
        return order

    async def get_order(self, session: AsyncSession, order_id: UUID) -> RadiologyOrder | None:
        result = await session.execute(
            select(RadiologyOrder)
            .where(RadiologyOrder.id == order_id, RadiologyOrder.deleted_at.is_(None))
            .options(selectinload(RadiologyOrder.study), selectinload(RadiologyOrder.reports))
        )
        return result.scalars().first()

    async def list_orders(
        self, session: AsyncSession, patient_id: UUID | None = None, ordering_doctor: UUID | None = None,
        status: str | None = None, modality_code: str | None = None, limit: int = 50, offset: int = 0,
    ) -> list[RadiologyOrder]:
        stmt = select(RadiologyOrder).where(RadiologyOrder.deleted_at.is_(None))
        if patient_id:
            stmt = stmt.where(RadiologyOrder.patient_id == patient_id)
        if ordering_doctor:
            stmt = stmt.where(RadiologyOrder.ordering_doctor == ordering_doctor)
        if status:
            stmt = stmt.where(RadiologyOrder.status == status)
        if modality_code:
            stmt = stmt.where(RadiologyOrder.modality_code == modality_code)
        stmt = stmt.order_by(RadiologyOrder.ordered_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_order(self, session: AsyncSession, order_id: UUID, payload: RadiologyOrderUpdate, actor_id: UUID) -> RadiologyOrder:
        order = await self.get_order(session, order_id)
        if not order:
            raise RadiologyError("ORDER_NOT_FOUND", "Order not found")
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(order, k, v)
        order.updated_by = actor_id
        order.version += 1
        await self._publish(session, "OrderUpdated", {"order_id": str(order.id), **data})
        return order

    async def cancel_order(self, session: AsyncSession, order_id: UUID, actor_id: UUID) -> RadiologyOrder:
        order = await self.get_order(session, order_id)
        if not order:
            raise RadiologyError("ORDER_NOT_FOUND", "Order not found")
        if order.status in ("COMPLETED", "CANCELLED"):
            raise RadiologyError("INVALID_STATE", f"Cannot cancel order in status {order.status}")
        order.status = "CANCELLED"
        order.updated_by = actor_id
        order.version += 1
        if order.study and order.study.status not in ("COMPLETED", "CANCELLED"):
            order.study.status = "CANCELLED"
            order.study.updated_by = actor_id
            order.study.version += 1
        return order

    # ------------------------ Study ------------------------

    async def create_study(self, session: AsyncSession, payload: StudyCreate, actor_id: UUID) -> Study:
        order = await self.get_order(session, payload.order_id)
        if not order:
            raise RadiologyError("ORDER_NOT_FOUND", "Order not found")

        existing = await session.execute(select(Study).where(Study.order_id == payload.order_id, Study.deleted_at.is_(None)))
        if existing.scalars().first():
            raise RadiologyError("STUDY_EXISTS", "Study already exists for this order")

        study = Study(
            order_id=payload.order_id,
            patient_id=payload.patient_id,
            modality_code=payload.modality_code,
            body_region=payload.body_region,
            study_instance_uid=payload.study_instance_uid,
            accession_number=payload.accession_number,
            status="SCHEDULED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(study)
        await session.flush()

        if order.status == "ORDERED":
            order.status = "SCHEDULED"
            order.updated_by = actor_id
            order.version += 1

        await self._publish(session, "StudyCreated", {"patient_id": str(study.patient_id), "modality": study.modality_code})
        return study

    async def get_study(self, session: AsyncSession, study_id: UUID) -> Study | None:
        return await session.get(Study, study_id)

    async def start_study(self, session: AsyncSession, study_id: UUID, payload: StudyStart, actor_id: UUID) -> Study:
        study = await session.get(Study, study_id)
        if not study:
            raise RadiologyError("STUDY_NOT_FOUND", "Study not found")
        if study.status != "SCHEDULED":
            raise RadiologyError("INVALID_STATE", f"Cannot start study in status {study.status}")

        study.status = "IN_PROGRESS"
        study.performed_by = payload.performed_by
        study.started_at = datetime.utcnow()
        study.updated_by = actor_id
        study.version += 1

        order = await self.get_order(session, study.order_id)
        if order and order.status in ("ORDERED", "SCHEDULED"):
            order.status = "PERFORMING"
            order.updated_by = actor_id
            order.version += 1

        await self._publish(session, "StudyUpdated", {"study_id": str(study.id), "status": "IN_PROGRESS"})
        return study

    async def complete_study(self, session: AsyncSession, study_id: UUID, payload: StudyComplete, actor_id: UUID) -> Study:
        study = await session.get(Study, study_id)
        if not study:
            raise RadiologyError("STUDY_NOT_FOUND", "Study not found")
        if study.status != "IN_PROGRESS":
            raise RadiologyError("INVALID_STATE", f"Cannot complete study in status {study.status}")

        study.status = "COMPLETED"
        study.completed_at = datetime.utcnow()
        study.technician_notes = payload.technician_notes
        study.updated_by = actor_id
        study.version += 1

        order = await self.get_order(session, study.order_id)
        if order and order.status == "PERFORMING":
            order.status = "COMPLETED"
            order.updated_by = actor_id
            order.version += 1

        await self._publish(session, "StudyUpdated", {"study_id": str(study.id), "status": "COMPLETED"})
        return study

    async def cancel_study(self, session: AsyncSession, study_id: UUID, actor_id: UUID) -> Study:
        study = await session.get(Study, study_id)
        if not study:
            raise RadiologyError("STUDY_NOT_FOUND", "Study not found")
        if study.status == "COMPLETED":
            raise RadiologyError("INVALID_STATE", "Cannot cancel completed study")

        study.status = "CANCELLED"
        study.updated_by = actor_id
        study.version += 1

        order = await self.get_order(session, study.order_id)
        if order and order.status not in ("COMPLETED", "CANCELLED"):
            order.status = "CANCELLED"
            order.updated_by = actor_id
            order.version += 1

        return study

    # ------------------------ Reports ------------------------

    async def create_report(self, session: AsyncSession, payload: RadiologyReportCreate, actor_id: UUID) -> RadiologyReport:
        order = await self.get_order(session, payload.order_id)
        if not order:
            raise RadiologyError("ORDER_NOT_FOUND", "Order not found")

        report = RadiologyReport(
            order_id=payload.order_id,
            patient_id=payload.patient_id,
            study_id=payload.study_id,
            findings=payload.findings,
            impression=payload.impression,
            recommendation=payload.recommendation,
            structured_report=payload.structured_report,
            status="DRAFT",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(report)
        await session.flush()

        await self._publish(
            session,
            "ReportCreated",
            {"patient_id": str(report.patient_id), "order_id": str(report.order_id)},
        )
        return report

    async def get_report(self, session: AsyncSession, report_id: UUID) -> RadiologyReport | None:
        return await session.get(RadiologyReport, report_id)

    async def list_reports(
        self, session: AsyncSession, patient_id: UUID | None = None, order_id: UUID | None = None,
        status: str | None = None, limit: int = 50, offset: int = 0,
    ) -> list[RadiologyReport]:
        stmt = select(RadiologyReport).where(RadiologyReport.deleted_at.is_(None))
        if patient_id:
            stmt = stmt.where(RadiologyReport.patient_id == patient_id)
        if order_id:
            stmt = stmt.where(RadiologyReport.order_id == order_id)
        if status:
            stmt = stmt.where(RadiologyReport.status == status)
        stmt = stmt.order_by(RadiologyReport.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_report(self, session: AsyncSession, report_id: UUID, payload: RadiologyReportUpdate, actor_id: UUID) -> RadiologyReport:
        report = await self.get_report(session, report_id)
        if not report:
            raise RadiologyError("REPORT_NOT_FOUND", "Report not found")
        if report.status == "FINAL":
            raise RadiologyError("INVALID_STATE", "Cannot update signed report")

        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(report, k, v)
        report.updated_by = actor_id
        report.version += 1

        await self._publish(session, "ReportUpdated", {"report_id": str(report.id), **data})
        return report

    async def sign_report(self, session: AsyncSession, report_id: UUID, payload: RadiologyReportSign, actor_id: UUID) -> RadiologyReport:
        report = await self.get_report(session, report_id)
        if not report:
            raise RadiologyError("REPORT_NOT_FOUND", "Report not found")
        if report.status == "CANCELLED":
            raise RadiologyError("INVALID_STATE", "Cannot sign cancelled report")

        report.status = "FINAL"
        report.signed_by = payload.signed_by
        report.signed_at = datetime.utcnow()
        report.updated_by = actor_id
        report.version += 1

        await self._publish(
            session,
            "ReportSigned",
            {"report_id": str(report.id), "signed_by": str(payload.signed_by)},
        )
        return report

    async def cancel_report(self, session: AsyncSession, report_id: UUID, actor_id: UUID) -> RadiologyReport:
        report = await self.get_report(session, report_id)
        if not report:
            raise RadiologyError("REPORT_NOT_FOUND", "Report not found")
        report.status = "CANCELLED"
        report.updated_by = actor_id
        report.version += 1
        return report


service = RadiologyService()
