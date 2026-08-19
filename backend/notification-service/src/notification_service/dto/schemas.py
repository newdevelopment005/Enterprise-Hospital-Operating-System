"""Pydantic schemas for the notification-service."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class NotificationTemplateIn(BaseModel):
    template_key: str = Field(min_length=1, max_length=255)
    channel: str = Field(pattern="^(email|sms|push|in_app)$")
    subject: str | None = Field(default=None, max_length=255)
    body_template: str = Field(min_length=1)
    is_active: bool = True


class NotificationTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_key: str
    channel: str
    subject: str | None
    body_template: str
    is_active: bool
    created_at: datetime


class NotificationCreate(BaseModel):
    """Request to send a notification (bypasses templates when body provided)."""

    notification_id: str | None = Field(default=None, max_length=64)
    template_key: str | None = Field(default=None, max_length=255)
    recipient: EmailStr | str
    channel: str = Field(pattern="^(email|sms|push|in_app)$")
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = None
    variables: dict[str, str] | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notification_id: str
    template_key: str | None
    recipient: str
    channel: str
    subject: str | None
    body: str
    status: str
    source: str | None
    correlation_id: str | None
    attempts: int
    sent_at: datetime | None
    created_at: datetime