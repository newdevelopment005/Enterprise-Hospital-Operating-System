"""Pydantic request/response schemas for the configuration-service."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeatureFlagIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    enabled: bool = False
    description: str | None = Field(default=None, max_length=1000)


class FeatureFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    enabled: bool
    description: str | None
    created_at: datetime
    updated_at: datetime


class ConfigurationEntryIn(BaseModel):
    config_key: str = Field(min_length=1, max_length=255)
    config_value: dict
    value_type: str = Field(default="string", max_length=50)
    description: str | None = Field(default=None, max_length=1000)


class ConfigurationEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    config_key: str
    config_value: dict
    value_type: str
    version: int
    description: str | None
    created_at: datetime
    updated_at: datetime


class ReferenceConfigAllOut(BaseModel):
    """Aggregate of all active reference configuration, used to seed other services."""

    flags: dict[str, bool]
    entries: dict[str, object]