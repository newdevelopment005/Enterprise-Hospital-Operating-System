from datetime import UTC, datetime
from uuid import UUID

from ehos_common.events import DomainEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workflow_service.dto.schemas import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowEventFire,
    WorkflowInstanceCreate,
)
from workflow_service.entity.models import WorkflowDefinition, WorkflowInstance, WorkflowTransition

TOPICS = {
    "DefinitionCreated": "workflow.definition.created",
    "DefinitionUpdated": "workflow.definition.updated",
    "InstanceCreated": "workflow.instance.created",
    "InstanceCompleted": "workflow.instance.completed",
    "InstanceCancelled": "workflow.instance.cancelled",
    "TransitionFired": "workflow.transition.fired",
}


class WorkflowError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class WorkflowService:
    """Workflow service: definitions, instances, transitions (state machine)."""

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
                source="workflow-service",
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

    # ------------------------ Definitions ------------------------

    async def create_definition(self, session: AsyncSession, payload: WorkflowDefinitionCreate, actor_id: UUID) -> WorkflowDefinition:
        existing = await session.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.key == payload.key, WorkflowDefinition.deleted_at.is_(None))
        )
        if existing.scalars().first():
            raise WorkflowError("DUPLICATE_KEY", f"Definition key '{payload.key}' already exists")

        defn = WorkflowDefinition(
            key=payload.key,
            name=payload.name,
            description=payload.description,
            states=payload.states,
            transitions=payload.transitions,
            initial_state=payload.initial_state,
            is_active=payload.is_active,
            version=1,
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(defn)
        await session.flush()
        await self._publish(session, "DefinitionCreated", {"key": defn.key, "name": defn.name})
        return defn

    async def get_definition(self, session: AsyncSession, definition_id: UUID) -> WorkflowDefinition | None:
        return await session.get(WorkflowDefinition, definition_id)

    async def list_definitions(self, session: AsyncSession, active_only: bool = True, limit: int = 50, offset: int = 0) -> list[WorkflowDefinition]:
        stmt = select(WorkflowDefinition).where(WorkflowDefinition.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(WorkflowDefinition.is_active.is_(True))
        stmt = stmt.order_by(WorkflowDefinition.key).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_definition(self, session: AsyncSession, definition_id: UUID, payload: WorkflowDefinitionUpdate, actor_id: UUID) -> WorkflowDefinition:
        defn = await self.get_definition(session, definition_id)
        if not defn:
            raise WorkflowError("DEFINITION_NOT_FOUND", "Definition not found")
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(defn, k, v)
        defn.updated_by = actor_id
        defn.model_version += 1
        await self._publish(session, "DefinitionUpdated", {"definition_id": str(defn.id), **data})
        return defn

    async def deactivate_definition(self, session: AsyncSession, definition_id: UUID, actor_id: UUID) -> WorkflowDefinition:
        defn = await self.get_definition(session, definition_id)
        if not defn:
            raise WorkflowError("DEFINITION_NOT_FOUND", "Definition not found")
        defn.is_active = False
        defn.deleted_at = datetime.utcnow()
        defn.deleted_by = actor_id
        defn.deletion_reason = "deactivated"
        defn.updated_by = actor_id
        defn.model_version += 1
        return defn

    # ------------------------ Instances ------------------------

    async def create_instance(self, session: AsyncSession, payload: WorkflowInstanceCreate, actor_id: UUID) -> WorkflowInstance:
        defn = await self.get_definition(session, payload.definition_id)
        if not defn:
            raise WorkflowError("DEFINITION_NOT_FOUND", "Definition not found")
        if not defn.is_active:
            raise WorkflowError("DEFINITION_INACTIVE", "Definition is not active")

        instance = WorkflowInstance(
            definition_id=payload.definition_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            patient_id=payload.patient_id,
            current_state=defn.initial_state,
            context=payload.context,
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(instance)
        await session.flush()

        await self._publish(
            session,
            "InstanceCreated",
            {"entity_type": instance.entity_type, "entity_id": str(instance.entity_id), "initial_state": instance.current_state},
        )
        return instance

    async def get_instance(self, session: AsyncSession, instance_id: UUID) -> WorkflowInstance | None:
        result = await session.execute(
            select(WorkflowInstance)
            .where(WorkflowInstance.id == instance_id, WorkflowInstance.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_instances(
        self, session: AsyncSession, entity_type: str | None = None, entity_id: UUID | None = None,
        patient_id: UUID | None = None, status: str | None = None, limit: int = 50, offset: int = 0,
    ) -> list[WorkflowInstance]:
        stmt = select(WorkflowInstance).where(WorkflowInstance.deleted_at.is_(None))
        if entity_type:
            stmt = stmt.where(WorkflowInstance.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(WorkflowInstance.entity_id == entity_id)
        if patient_id:
            stmt = stmt.where(WorkflowInstance.patient_id == patient_id)
        if status:
            stmt = stmt.where(WorkflowInstance.status == status)
        stmt = stmt.order_by(WorkflowInstance.started_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------ Transitions (fire event) ------------------------

    async def fire_event(self, session: AsyncSession, instance_id: UUID, payload: WorkflowEventFire, actor_id: UUID) -> WorkflowInstance:
        instance = await self.get_instance(session, instance_id)
        if not instance:
            raise WorkflowError("INSTANCE_NOT_FOUND", "Instance not found")
        if instance.status != "ACTIVE":
            raise WorkflowError("INVALID_STATE", f"Cannot fire event on instance in status {instance.status}")

        defn = await self.get_definition(session, instance.definition_id)
        if not defn:
            raise WorkflowError("DEFINITION_NOT_FOUND", "Definition not found")

        transitions = defn.transitions or {}
        current_transitions = transitions.get(instance.current_state, {})
        to_state = current_transitions.get(payload.event)

        if to_state is None:
            raise WorkflowError("INVALID_TRANSITION", f"No transition for event '{payload.event}' from state '{instance.current_state}'")

        # Record transition
        transition = WorkflowTransition(
            instance_id=instance.id,
            from_state=instance.current_state,
            to_state=to_state,
            event=payload.event,
            actor_id=actor_id,
            comment=payload.comment,
            event_metadata=payload.metadata,
            status="COMPLETED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(transition)

        # Update instance
        instance.current_state = to_state
        instance.updated_by = actor_id
        instance.model_version += 1

        # Check if terminal state (no outgoing transitions)
        next_transitions = transitions.get(to_state, {})
        if not next_transitions:
            instance.status = "COMPLETED"
            instance.completed_at = datetime.utcnow()
            await self._publish(session, "InstanceCompleted", {"instance_id": str(instance.id), "final_state": to_state})
        else:
            await self._publish(
                session,
                "TransitionFired",
                {"instance_id": str(instance.id), "from": transition.from_state, "to": to_state, "event": payload.event},
            )

        return instance

    async def cancel_instance(self, session: AsyncSession, instance_id: UUID, actor_id: UUID) -> WorkflowInstance:
        instance = await self.get_instance(session, instance_id)
        if not instance:
            raise WorkflowError("INSTANCE_NOT_FOUND", "Instance not found")
        if instance.status != "ACTIVE":
            raise WorkflowError("INVALID_STATE", f"Cannot cancel instance in status {instance.status}")

        instance.status = "CANCELLED"
        instance.completed_at = datetime.utcnow()
        instance.updated_by = actor_id
        instance.model_version += 1

        await self._publish(session, "InstanceCancelled", {"instance_id": str(instance.id)})
        return instance

    async def pause_instance(self, session: AsyncSession, instance_id: UUID, actor_id: UUID) -> WorkflowInstance:
        instance = await self.get_instance(session, instance_id)
        if not instance:
            raise WorkflowError("INSTANCE_NOT_FOUND", "Instance not found")
        if instance.status != "ACTIVE":
            raise WorkflowError("INVALID_STATE", f"Cannot pause instance in status {instance.status}")

        instance.status = "PAUSED"
        instance.updated_by = actor_id
        instance.model_version += 1
        return instance

    async def resume_instance(self, session: AsyncSession, instance_id: UUID, actor_id: UUID) -> WorkflowInstance:
        instance = await self.get_instance(session, instance_id)
        if not instance:
            raise WorkflowError("INSTANCE_NOT_FOUND", "Instance not found")
        if instance.status != "PAUSED":
            raise WorkflowError("INVALID_STATE", f"Cannot resume instance in status {instance.status}")

        instance.status = "ACTIVE"
        instance.updated_by = actor_id
        instance.model_version += 1
        return instance

    async def list_transitions(self, session: AsyncSession, instance_id: UUID) -> list[WorkflowTransition]:
        stmt = select(WorkflowTransition).where(
            WorkflowTransition.instance_id == instance_id, WorkflowTransition.deleted_at.is_(None)
        ).order_by(WorkflowTransition.performed_at)
        result = await session.execute(stmt)
        return list(result.scalars().all())


service = WorkflowService()
