"""Database models for the notification-service."""

from datetime import datetime

from ehos_common.db import AuditMixin, Base
from sqlalchemy import JSON, BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

NOTIFICATION_STATUS = ("queued", "sending", "delivered", "failed")
NOTIFICATION_CHANNELS = ("email", "sms", "push", "in_app")


class NotificationTemplate(Base, AuditMixin):
    """A reusable notification template keyed by type and channel."""

    __tablename__ = "notification_templates"

    template_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class Notification(Base, AuditMixin):
    """A single notification delivery attempt and its lifecycle."""

    __tablename__ = "notifications"

    notification_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    template_key: Mapped[str] = mapped_column(String(255), nullable=True)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)