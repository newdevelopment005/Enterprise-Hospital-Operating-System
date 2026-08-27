"""Workflow service tests."""

import uuid

import pytest

from workflow_service.dto.schemas import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowEventFire,
    WorkflowInstanceCreate,
)
from workflow_service.service.workflow_service import WorkflowError


# Admission workflow: NEW → TRIAGED → ADMITTED → DISCHARGED
ADMISSION_DEF = WorkflowDefinitionCreate(
    key="ADMISSION",
    name="Patient Admission",
    description="Standard patient admission workflow",
    initial_state="NEW",
    states={"NEW": {}, "TRIAGED": {}, "ADMITTED": {}, "DISCHARGED": {}},
    transitions={
        "NEW": {"triage": "TRIAGED", "cancel": "CANCELLED"},
        "TRIAGED": {"admit": "ADMITTED", "cancel": "CANCELLED"},
        "ADMITTED": {"discharge": "DISCHARGED", "cancel": "CANCELLED"},
    },
)


async def _create_def(session, svc, actor_id, key="ADMISSION"):
    defn = WorkflowDefinitionCreate(
        key=key, name=f"{key} Workflow", initial_state="OPEN",
        states={"OPEN": {}, "CLOSED": {}},
        transitions={"OPEN": {"close": "CLOSED"}},
    )
    return await svc.create_definition(session, defn, actor_id)


class TestWorkflowDefinitions:
    async def test_create_definition(self, session, svc, actor_id):
        defn = await svc.create_definition(session, ADMISSION_DEF, actor_id)
        assert defn.id
        assert defn.key == "ADMISSION"
        assert defn.initial_state == "NEW"
        assert defn.status == "ACTIVE"

    async def test_duplicate_key_rejected(self, session, svc, actor_id):
        await svc.create_definition(session, ADMISSION_DEF, actor_id)
        with pytest.raises(WorkflowError, match="already exists"):
            await svc.create_definition(session, ADMISSION_DEF, actor_id)

    async def test_list_definitions(self, session, svc, actor_id):
        await svc.create_definition(session, ADMISSION_DEF, actor_id)
        items = await svc.list_definitions(session)
        assert len(items) == 1

    async def test_update_definition(self, session, svc, actor_id):
        defn = await svc.create_definition(session, ADMISSION_DEF, actor_id)
        updated = await svc.update_definition(session, defn.id, WorkflowDefinitionUpdate(name="Patient Admission v2"), actor_id)
        assert updated.name == "Patient Admission v2"
        assert updated.model_version == 2

    async def test_deactivate_definition(self, session, svc, actor_id):
        defn = await svc.create_definition(session, ADMISSION_DEF, actor_id)
        await svc.deactivate_definition(session, defn.id, actor_id)
        items = await svc.list_definitions(session)
        assert len(items) == 0


class TestWorkflowInstances:
    async def _create_admission_def(self, session, svc, actor_id):
        return await svc.create_definition(session, ADMISSION_DEF, actor_id)

    async def test_create_instance(self, session, svc, actor_id, patient_id):
        defn = await self._create_admission_def(session, svc, actor_id)
        instance = await svc.create_instance(
            session, WorkflowInstanceCreate(
                definition_id=defn.id, entity_type="patient", entity_id=patient_id,
                patient_id=patient_id, context={"chief_complaint": "chest pain"},
            ), actor_id,
        )
        assert instance.id
        assert instance.current_state == "NEW"
        assert instance.status == "ACTIVE"

    async def test_create_instance_inactive_def(self, session, svc, actor_id, patient_id):
        defn = await self._create_admission_def(session, svc, actor_id)
        await svc.deactivate_definition(session, defn.id, actor_id)
        with pytest.raises(WorkflowError, match="not active"):
            await svc.create_instance(
                session, WorkflowInstanceCreate(definition_id=defn.id, entity_type="patient", entity_id=patient_id), actor_id,
            )

    async def test_list_instances(self, session, svc, actor_id, patient_id):
        defn = await self._create_admission_def(session, svc, actor_id)
        await svc.create_instance(session, WorkflowInstanceCreate(definition_id=defn.id, entity_type="patient", entity_id=patient_id, patient_id=patient_id), actor_id)
        items = await svc.list_instances(session, patient_id=patient_id)
        assert len(items) == 1

    async def test_list_by_entity(self, session, svc, actor_id, patient_id):
        defn = await self._create_admission_def(session, svc, actor_id)
        eid = uuid.uuid4()
        await svc.create_instance(session, WorkflowInstanceCreate(definition_id=defn.id, entity_type="encounter", entity_id=eid), actor_id)
        items = await svc.list_instances(session, entity_type="encounter", entity_id=eid)
        assert len(items) == 1


class TestWorkflowTransitions:
    async def _setup(self, session, svc, actor_id, patient_id):
        defn = await svc.create_definition(session, ADMISSION_DEF, actor_id)
        instance = await svc.create_instance(
            session, WorkflowInstanceCreate(definition_id=defn.id, entity_type="patient", entity_id=patient_id, patient_id=patient_id), actor_id,
        )
        return defn, instance

    async def test_fire_valid_transition(self, session, svc, actor_id, patient_id):
        _, instance = await self._setup(session, svc, actor_id, patient_id)
        updated = await svc.fire_event(session, instance.id, WorkflowEventFire(event="triage", actor_id=actor_id), actor_id)
        assert updated.current_state == "TRIAGED"
        assert updated.status == "ACTIVE"

    async def test_fire_complete_workflow(self, session, svc, actor_id, patient_id):
        _, instance = await self._setup(session, svc, actor_id, patient_id)
        await svc.fire_event(session, instance.id, WorkflowEventFire(event="triage", actor_id=actor_id), actor_id)
        await svc.fire_event(session, instance.id, WorkflowEventFire(event="admit", actor_id=actor_id), actor_id)
        completed = await svc.fire_event(session, instance.id, WorkflowEventFire(event="discharge", actor_id=actor_id), actor_id)
        assert completed.current_state == "DISCHARGED"
        assert completed.status == "COMPLETED"
        assert completed.completed_at is not None

    async def test_fire_invalid_transition(self, session, svc, actor_id, patient_id):
        _, instance = await self._setup(session, svc, actor_id, patient_id)
        with pytest.raises(WorkflowError, match="No transition"):
            await svc.fire_event(session, instance.id, WorkflowEventFire(event="admit", actor_id=actor_id), actor_id)

    async def test_fire_event_on_completed_rejected(self, session, svc, actor_id, patient_id):
        _, instance = await self._setup(session, svc, actor_id, patient_id)
        await svc.fire_event(session, instance.id, WorkflowEventFire(event="triage", actor_id=actor_id), actor_id)
        await svc.fire_event(session, instance.id, WorkflowEventFire(event="admit", actor_id=actor_id), actor_id)
        await svc.fire_event(session, instance.id, WorkflowEventFire(event="discharge", actor_id=actor_id), actor_id)
        with pytest.raises(WorkflowError, match="Cannot fire event"):
            await svc.fire_event(session, instance.id, WorkflowEventFire(event="cancel", actor_id=actor_id), actor_id)

    async def test_cancel_instance(self, session, svc, actor_id, patient_id):
        _, instance = await self._setup(session, svc, actor_id, patient_id)
        cancelled = await svc.cancel_instance(session, instance.id, actor_id)
        assert cancelled.status == "CANCELLED"

    async def test_pause_and_resume(self, session, svc, actor_id, patient_id):
        _, instance = await self._setup(session, svc, actor_id, patient_id)
        paused = await svc.pause_instance(session, instance.id, actor_id)
        assert paused.status == "PAUSED"
        resumed = await svc.resume_instance(session, instance.id, actor_id)
        assert resumed.status == "ACTIVE"

    async def test_list_transitions(self, session, svc, actor_id, patient_id):
        _, instance = await self._setup(session, svc, actor_id, patient_id)
        await svc.fire_event(session, instance.id, WorkflowEventFire(event="triage", actor_id=actor_id, comment="Initial triage"), actor_id)
        await svc.fire_event(session, instance.id, WorkflowEventFire(event="admit", actor_id=actor_id), actor_id)
        transitions = await svc.list_transitions(session, instance.id)
        assert len(transitions) == 2
        assert transitions[0].from_state == "NEW"
        assert transitions[0].to_state == "TRIAGED"
        assert transitions[1].from_state == "TRIAGED"
        assert transitions[1].to_state == "ADMITTED"
