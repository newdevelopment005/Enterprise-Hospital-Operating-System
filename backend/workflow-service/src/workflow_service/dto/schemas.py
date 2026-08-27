from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---- WorkflowDefinition ----


class WorkflowDefinitionBase(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    states: dict | None = None
    transitions: dict | None = None
    initial_state: str = Field(min_length=1, max_length=64)
    is_active: bool = True


class WorkflowDefinitionCreate(WorkflowDefinitionBase):
    pass


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    states: dict | None = None
    transitions: dict | None = None
    initial_state: str | None = Field(default=None, min_length=1, max_length=64)
    is_active: bool | None = None


class WorkflowDefinitionRead(WorkflowDefinitionBase):
    id: UUID
    version: int
    status: str
    created_at: datetime
    updated_at: datetime
    model_version: int

    model_config = ConfigDict(from_attributes=True)


# ---- WorkflowInstance ----


class WorkflowInstanceBase(BaseModel):
    definition_id: UUID
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: UUID
    patient_id: UUID | None = None
    context: dict | None = None


class WorkflowInstanceCreate(WorkflowInstanceBase):
    pass


class WorkflowInstanceRead(WorkflowInstanceBase):
    id: UUID
    current_state: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    model_version: int

    model_config = ConfigDict(from_attributes=True)


# ---- WorkflowTransition (fire event) ----


class WorkflowEventFire(BaseModel):
    event: str = Field(min_length=1, max_length=64)
    actor_id: UUID
    comment: str | None = None
    metadata: dict | None = None


class WorkflowTransitionRead(BaseModel):
    id: UUID
    instance_id: UUID
    from_state: str
    to_state: str
    event: str
    actor_id: UUID
    comment: str | None = None
    event_metadata: dict | None = None
    performed_at: datetime
    created_at: datetime
    status: str
    model_version: int

    model_config = ConfigDict(from_attributes=True)


# ---- Pagination ----


class PaginatedResponse(BaseModel):
    items: list
    total: int
    limit: int
    offset: int
