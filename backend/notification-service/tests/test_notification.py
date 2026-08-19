"""Tests for the notification-service."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from notification_service.dto.schemas import NotificationCreate, NotificationTemplateIn
from notification_service.entity.models import Base
from notification_service.service.notification_service import NotificationService


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _adapters(records: list, *, fail: bool = False) -> dict:
    class Email:
        name = "email"

        def send(self, *, recipient, subject, body):
            records.append({"recipient": recipient, "subject": subject, "body": body})
            if fail:
                raise RuntimeError("provider down")
            return {"messageId": "1"}

    return {"email": Email()}


async def test_template_rendering_binds_variables():
    service = NotificationService({})
    rendered = service.render_body("Hello {{name}}, appointment on {{date}}", {"name": "Ali", "date": "Monday"})
    assert rendered == "Hello Ali, appointment on Monday"


async def test_send_email_success(session):
    records = []
    service = NotificationService(_adapters(records))
    notification = await service.create_and_send(
        session,
        NotificationCreate(recipient="ali@hospital.example", channel="email", body="Welcome", subject="Hi"),
    )
    assert notification.status == "delivered"
    assert records == [{"recipient": "ali@hospital.example", "subject": "Hi", "body": "Welcome"}]


async def test_send_failure_after_retries(session):
    records = []
    service = NotificationService(_adapters(records, fail=True))
    notification = await service.create_and_send(
        session,
        NotificationCreate(recipient="ali@hospital.example", channel="email", body="x"),
    )
    assert notification.status == "failed"
    assert notification.attempts == 3


async def test_upsert_template_increments(session):
    service = NotificationService({})
    first_data = NotificationTemplateIn(
        template_key="appointment_confirmed", channel="email", body_template="Confirmed {{date}}"
    )
    second_data = NotificationTemplateIn(
        template_key="appointment_confirmed", channel="email", body_template="Updated {{date}}"
    )
    first = await service.upsert_template(session, first_data)
    second = await service.upsert_template(session, second_data)
    assert first.id == second.id
    assert second.body_template == "Updated {{date}}"