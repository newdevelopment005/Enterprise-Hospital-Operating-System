from datetime import UTC, datetime
from uuid import UUID

from ehos_common.events import DomainEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reporting_service.dto.schemas import (
    ReportDefinitionCreate,
    ReportDefinitionUpdate,
    ReportInstanceCreate,
    ScheduledReportCreate,
    ScheduledReportUpdate,
)
from reporting_service.entity.models import ReportDefinition, ReportInstance, ScheduledReport

TOPICS = {
    "ReportRequested": "reporting.instance.requested",
    "ReportCompleted": "reporting.instance.completed",
    "ReportFailed": "reporting.instance.failed",
    "ScheduledReportCreated": "reporting.scheduled.created",
}


class ReportingError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ReportingService:
    """Reporting service: report definitions, instances, scheduled reports."""

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
                source="reporting-service",
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

    # ── Report Definitions ────────────────────────────────────────────────────

    async def create_definition(self, session: AsyncSession, payload: ReportDefinitionCreate, actor_id: UUID) -> ReportDefinition:
        defn = ReportDefinition(
            name=payload.name,
            report_type=payload.report_type,
            description=payload.description,
            parameters_schema=payload.parameters_schema,
            is_active=payload.is_active,
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(defn)
        await session.flush()
        return defn

    async def get_definition(self, session: AsyncSession, definition_id: UUID) -> ReportDefinition | None:
        return await session.get(ReportDefinition, definition_id)

    async def list_definitions(self, session: AsyncSession, report_type: str | None = None, active_only: bool = True, limit: int = 50, offset: int = 0) -> list[ReportDefinition]:
        stmt = select(ReportDefinition).where(ReportDefinition.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(ReportDefinition.is_active.is_(True))
        if report_type:
            stmt = stmt.where(ReportDefinition.report_type == report_type)
        stmt = stmt.order_by(ReportDefinition.name).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_definition(self, session: AsyncSession, definition_id: UUID, payload: ReportDefinitionUpdate, actor_id: UUID) -> ReportDefinition:
        defn = await self.get_definition(session, definition_id)
        if not defn:
            raise ReportingError("DEFINITION_NOT_FOUND", "Report definition not found")
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(defn, k, v)
        defn.updated_by = actor_id
        defn.model_version += 1
        return defn

    # ── Report Instances ──────────────────────────────────────────────────────

    async def create_instance(self, session: AsyncSession, payload: ReportInstanceCreate, actor_id: UUID) -> ReportInstance:
        defn = await self.get_definition(session, payload.report_definition_id)
        if not defn:
            raise ReportingError("DEFINITION_NOT_FOUND", "Report definition not found")
        if not defn.is_active:
            raise ReportingError("INACTIVE_DEFINITION", "Cannot run inactive report")

        instance = ReportInstance(
            report_definition_id=payload.report_definition_id,
            parameters=payload.parameters,
            requested_by=payload.requested_by,
            status="QUEUED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(instance)
        await session.flush()
        await self._publish(session, "ReportRequested", {"instance_id": str(instance.id), "definition_id": str(defn.id)})
        return instance

    async def get_instance(self, session: AsyncSession, instance_id: UUID) -> ReportInstance | None:
        return await session.get(ReportInstance, instance_id)

    async def list_instances(self, session: AsyncSession, definition_id: UUID | None = None, requested_by: UUID | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> list[ReportInstance]:
        stmt = select(ReportInstance).where(ReportInstance.deleted_at.is_(None))
        if definition_id:
            stmt = stmt.where(ReportInstance.report_definition_id == definition_id)
        if requested_by:
            stmt = stmt.where(ReportInstance.requested_by == requested_by)
        if status:
            stmt = stmt.where(ReportInstance.status == status)
        stmt = stmt.order_by(ReportInstance.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def start_instance(self, session: AsyncSession, instance_id: UUID, actor_id: UUID) -> ReportInstance:
        instance = await self.get_instance(session, instance_id)
        if not instance:
            raise ReportingError("INSTANCE_NOT_FOUND", "Instance not found")
        if instance.status != "QUEUED":
            raise ReportingError("INVALID_STATE", "Only QUEUED instances can be started")
        instance.status = "RUNNING"
        instance.started_at = datetime.now(UTC)
        instance.updated_by = actor_id
        instance.model_version += 1
        return instance

    async def complete_instance(self, session: AsyncSession, instance_id: UUID, result_data: dict, actor_id: UUID) -> ReportInstance:
        instance = await self.get_instance(session, instance_id)
        if not instance:
            raise ReportingError("INSTANCE_NOT_FOUND", "Instance not found")
        if instance.status != "RUNNING":
            raise ReportingError("INVALID_STATE", "Only RUNNING instances can be completed")
        instance.status = "COMPLETED"
        instance.result_data = result_data
        instance.completed_at = datetime.now(UTC)
        instance.updated_by = actor_id
        instance.model_version += 1
        await self._publish(session, "ReportCompleted", {"instance_id": str(instance.id)})
        return instance

    async def fail_instance(self, session: AsyncSession, instance_id: UUID, error_message: str, actor_id: UUID) -> ReportInstance:
        instance = await self.get_instance(session, instance_id)
        if not instance:
            raise ReportingError("INSTANCE_NOT_FOUND", "Instance not found")
        instance.status = "FAILED"
        instance.error_message = error_message
        instance.completed_at = datetime.now(UTC)
        instance.updated_by = actor_id
        instance.model_version += 1
        await self._publish(session, "ReportFailed", {"instance_id": str(instance.id), "error": error_message})
        return instance

    async def cancel_instance(self, session: AsyncSession, instance_id: UUID, actor_id: UUID) -> ReportInstance:
        instance = await self.get_instance(session, instance_id)
        if not instance:
            raise ReportingError("INSTANCE_NOT_FOUND", "Instance not found")
        if instance.status in ("COMPLETED", "CANCELLED"):
            raise ReportingError("INVALID_STATE", f"Cannot cancel {instance.status} instance")
        instance.status = "CANCELLED"
        instance.updated_by = actor_id
        instance.model_version += 1
        return instance

    # ── Scheduled Reports ─────────────────────────────────────────────────────

    async def create_scheduled(self, session: AsyncSession, payload: ScheduledReportCreate, actor_id: UUID) -> ScheduledReport:
        defn = await self.get_definition(session, payload.report_definition_id)
        if not defn:
            raise ReportingError("DEFINITION_NOT_FOUND", "Report definition not found")
        if not defn.is_active:
            raise ReportingError("INACTIVE_DEFINITION", "Cannot schedule inactive report")
        sched = ScheduledReport(
            report_definition_id=payload.report_definition_id,
            schedule_cron=payload.schedule_cron,
            parameters=payload.parameters,
            delivery_email=payload.delivery_email,
            is_active=payload.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(sched)
        await session.flush()
        await self._publish(session, "ScheduledReportCreated", {"definition_id": str(defn.id), "cron": sched.schedule_cron})
        return sched

    async def get_scheduled(self, session: AsyncSession, scheduled_id: UUID) -> ScheduledReport | None:
        return await session.get(ScheduledReport, scheduled_id)

    async def list_scheduled(self, session: AsyncSession, definition_id: UUID | None = None, active_only: bool = True, limit: int = 50, offset: int = 0) -> list[ScheduledReport]:
        stmt = select(ScheduledReport).where(ScheduledReport.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(ScheduledReport.is_active.is_(True))
        if definition_id:
            stmt = stmt.where(ScheduledReport.report_definition_id == definition_id)
        stmt = stmt.order_by(ScheduledReport.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_scheduled(self, session: AsyncSession, scheduled_id: UUID, payload: ScheduledReportUpdate, actor_id: UUID) -> ScheduledReport:
        sched = await self.get_scheduled(session, scheduled_id)
        if not sched:
            raise ReportingError("SCHEDULED_NOT_FOUND", "Scheduled report not found")
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(sched, k, v)
        sched.updated_by = actor_id
        sched.model_version += 1
        return sched

    async def deactivate_scheduled(self, session: AsyncSession, scheduled_id: UUID, actor_id: UUID) -> ScheduledReport:
        sched = await self.get_scheduled(session, scheduled_id)
        if not sched:
            raise ReportingError("SCHEDULED_NOT_FOUND", "Scheduled report not found")
        sched.is_active = False
        sched.updated_by = actor_id
        sched.model_version += 1
        return sched


service = ReportingService()
