"""Template rendering and notification orchestration."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification_service.channel.adapters import ChannelAdapter
from notification_service.dto.schemas import NotificationCreate
from notification_service.entity.models import Notification, NotificationTemplate

log = structlog.get_logger("notification-service")

MAX_ATTEMPTS = 3


class NotificationService:
    def __init__(self, adapters: dict[str, ChannelAdapter]):
        self.adapters = adapters

    async def render_template(
        self, session: AsyncSession, template_key: str, variables: dict[str, str] | None
    ) -> NotificationTemplate | None:
        template = (
            await session.execute(select(NotificationTemplate).where(NotificationTemplate.template_key == template_key))
        ).scalar_one_or_none()
        return template

    async def upsert_template(self, session: AsyncSession, data) -> NotificationTemplate:
        result = await session.execute(
            select(NotificationTemplate).where(NotificationTemplate.template_key == data.template_key)
        )
        template = result.scalar_one_or_none()
        if template is None:
            template = NotificationTemplate(
                template_key=data.template_key,
                channel=data.channel,
                subject=data.subject,
                body_template=data.body_template,
                is_active=data.is_active,
            )
            session.add(template)
        else:
            template.channel = data.channel
            template.subject = data.subject
            template.body_template = data.body_template
            template.is_active = data.is_active
        await session.flush()
        return template

    @staticmethod
    def render_body(template: str, variables: dict[str, str] | None) -> str:
        if not variables:
            return template
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace("{{" + key + "}}", value).replace("{{ " + key + " }}", value)
        return rendered

    async def create_and_send(
        self,
        session: AsyncSession,
        data: NotificationCreate,
        source: str | None = None,
        correlation_id: str | None = None,
    ) -> Notification:
        body = data.body
        subject = data.subject
        if data.template_key:
            template = await self.render_template(session, data.template_key, data.variables)
            if template is not None:
                body = self.render_body(template.body_template, data.variables)
                subject = subject or template.subject

        notification_id = data.notification_id or str(uuid.uuid4())
        # Idempotency for at-least-once delivery: a caller-supplied
        # notification_id (consumers pass the eventId) makes redelivery a no-op.
        existing = (
            await session.execute(select(Notification).where(Notification.notification_id == notification_id))
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        notification = Notification(
            notification_id=notification_id,
            template_key=data.template_key,
            recipient=str(data.recipient),
            channel=data.channel,
            subject=subject,
            body=body or "",
            status="queued",
            source=source,
            correlation_id=correlation_id,
        )
        session.add(notification)
        await session.flush()

        adapter = self.adapters.get(data.channel)
        if adapter is None:
            notification.status = "failed"
            notification.provider_response = {"error": f"Unknown channel {data.channel}"}
            return notification

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = adapter.send(recipient=str(data.recipient), subject=subject, body=body or "")
                notification.status = "delivered"
                notification.attempts = attempt
                notification.sent_at = datetime.now(UTC)
                notification.provider_response = response
                break
            except Exception as exc:
                notification.attempts = attempt
                log.warning("delivery_attempt_failed", channel=data.channel, attempt=attempt, error=str(exc))
                if attempt == MAX_ATTEMPTS:
                    notification.status = "failed"
                    notification.provider_response = {"error": str(exc)}
        return notification