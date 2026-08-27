import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from reporting_service.dto.schemas import (
    ReportDefinitionCreate,
    ReportDefinitionUpdate,
    ReportInstanceCreate,
    ScheduledReportCreate,
    ScheduledReportUpdate,
)
from reporting_service.service.reporting_service import ReportingService, ReportingError


def _uid():
    return uuid.uuid4()


def _defn_payload(**overrides):
    d = dict(name="Patient Summary", report_type="PATIENT_SUMMARY", description="Shows patient encounters")
    d.update(overrides)
    return ReportDefinitionCreate(**d)


def _inst_payload(**overrides):
    d = dict(report_definition_id=_uid(), requested_by=_uid())
    d.update(overrides)
    return ReportInstanceCreate(**d)


def _sched_payload(**overrides):
    d = dict(report_definition_id=_uid(), schedule_cron="0 0 * * *")
    d.update(overrides)
    return ScheduledReportCreate(**d)


# ── Definitions ─────────────────────────────────────────────────────────────────


class TestReportDefinitions:
    async def test_create_definition(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        assert defn.id
        assert defn.status == "ACTIVE"
        assert defn.report_type == "PATIENT_SUMMARY"

    async def test_get_definition(self, db: AsyncSession, rpt_service: ReportingService):
        created = await rpt_service.create_definition(db, _defn_payload(), _uid())
        got = await rpt_service.get_definition(db, created.id)
        assert got is not None
        assert got.id == created.id

    async def test_list_definitions(self, db: AsyncSession, rpt_service: ReportingService):
        await rpt_service.create_definition(db, _defn_payload(name="A"), _uid())
        await rpt_service.create_definition(db, _defn_payload(name="B", report_type="FINANCIAL"), _uid())
        all_defs = await rpt_service.list_definitions(db)
        assert len(all_defs) == 2
        fin_defs = await rpt_service.list_definitions(db, report_type="FINANCIAL")
        assert len(fin_defs) == 1

    async def test_update_definition(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        updated = await rpt_service.update_definition(db, defn.id, ReportDefinitionUpdate(name="New Name"), _uid())
        assert updated.name == "New Name"
        assert updated.model_version == 2

    async def test_deactivate_definition(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        await rpt_service.update_definition(db, defn.id, ReportDefinitionUpdate(is_active=False), _uid())
        active = await rpt_service.list_definitions(db, active_only=True)
        assert len(active) == 0

    async def test_get_nonexistent_definition(self, db: AsyncSession, rpt_service: ReportingService):
        assert await rpt_service.get_definition(db, _uid()) is None


# ── Instances ───────────────────────────────────────────────────────────────────


class TestReportInstances:
    async def test_create_instance(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        inst = await rpt_service.create_instance(db, _inst_payload(report_definition_id=defn.id), _uid())
        assert inst.id
        assert inst.status == "QUEUED"

    async def test_create_instance_inactive_def_raises(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        await rpt_service.update_definition(db, defn.id, ReportDefinitionUpdate(is_active=False), _uid())
        with pytest.raises(ReportingError, match="inactive"):
            await rpt_service.create_instance(db, _inst_payload(report_definition_id=defn.id), _uid())

    async def test_start_instance(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        inst = await rpt_service.create_instance(db, _inst_payload(report_definition_id=defn.id), _uid())
        running = await rpt_service.start_instance(db, inst.id, _uid())
        assert running.status == "RUNNING"
        assert running.started_at is not None

    async def test_complete_instance(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        inst = await rpt_service.create_instance(db, _inst_payload(report_definition_id=defn.id), _uid())
        await rpt_service.start_instance(db, inst.id, _uid())
        done = await rpt_service.complete_instance(db, inst.id, {"rows": 42}, _uid())
        assert done.status == "COMPLETED"
        assert done.result_data == {"rows": 42}
        assert done.completed_at is not None

    async def test_fail_instance(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        inst = await rpt_service.create_instance(db, _inst_payload(report_definition_id=defn.id), _uid())
        await rpt_service.start_instance(db, inst.id, _uid())
        failed = await rpt_service.fail_instance(db, inst.id, "timeout", _uid())
        assert failed.status == "FAILED"
        assert failed.error_message == "timeout"

    async def test_cancel_instance(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        inst = await rpt_service.create_instance(db, _inst_payload(report_definition_id=defn.id), _uid())
        cancelled = await rpt_service.cancel_instance(db, inst.id, _uid())
        assert cancelled.status == "CANCELLED"

    async def test_cancel_completed_instance_raises(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        inst = await rpt_service.create_instance(db, _inst_payload(report_definition_id=defn.id), _uid())
        await rpt_service.start_instance(db, inst.id, _uid())
        await rpt_service.complete_instance(db, inst.id, {}, _uid())
        with pytest.raises(ReportingError, match="COMPLETED"):
            await rpt_service.cancel_instance(db, inst.id, _uid())

    async def test_list_instances(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        for _ in range(3):
            await rpt_service.create_instance(db, _inst_payload(report_definition_id=defn.id), _uid())
        items = await rpt_service.list_instances(db, definition_id=defn.id)
        assert len(items) == 3


# ── Scheduled Reports ───────────────────────────────────────────────────────────


class TestScheduledReports:
    async def test_create_scheduled(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        sched = await rpt_service.create_scheduled(db, _sched_payload(report_definition_id=defn.id), _uid())
        assert sched.id
        assert sched.schedule_cron == "0 0 * * *"

    async def test_create_scheduled_inactive_def_raises(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        await rpt_service.update_definition(db, defn.id, ReportDefinitionUpdate(is_active=False), _uid())
        with pytest.raises(ReportingError, match="inactive"):
            await rpt_service.create_scheduled(db, _sched_payload(report_definition_id=defn.id), _uid())

    async def test_list_scheduled(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        for i in range(2):
            await rpt_service.create_scheduled(db, _sched_payload(report_definition_id=defn.id, schedule_cron=f"0 {i} * * *"), _uid())
        items = await rpt_service.list_scheduled(db, definition_id=defn.id)
        assert len(items) == 2

    async def test_update_scheduled(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        sched = await rpt_service.create_scheduled(db, _sched_payload(report_definition_id=defn.id), _uid())
        updated = await rpt_service.update_scheduled(db, sched.id, ScheduledReportUpdate(schedule_cron="0 12 * * *"), _uid())
        assert updated.schedule_cron == "0 12 * * *"
        assert updated.model_version == 2

    async def test_deactivate_scheduled(self, db: AsyncSession, rpt_service: ReportingService):
        defn = await rpt_service.create_definition(db, _defn_payload(), _uid())
        sched = await rpt_service.create_scheduled(db, _sched_payload(report_definition_id=defn.id), _uid())
        deactivated = await rpt_service.deactivate_scheduled(db, sched.id, _uid())
        assert deactivated.is_active is False

    async def test_get_nonexistent_scheduled(self, db: AsyncSession, rpt_service: ReportingService):
        assert await rpt_service.get_scheduled(db, _uid()) is None
