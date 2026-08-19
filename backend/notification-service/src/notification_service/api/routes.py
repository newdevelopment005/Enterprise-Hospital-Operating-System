"""REST API for the notification-service."""

from collections.abc import AsyncIterator

from ehos_common.api import NotFoundError, success_response
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from notification_service.dto.schemas import (
    NotificationCreate,
    NotificationTemplateIn,
)
from notification_service.service.notification_service import NotificationService

router = APIRouter(prefix="/api/v1", tags=["notifications"])


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_service(request: Request) -> NotificationService:
    return request.app.state.notification_service


SERVICE = Depends(get_service)


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    data: NotificationTemplateIn,
    session: AsyncSession = Depends(get_session),
    service: NotificationService = SERVICE,
) -> dict:
    template = await service.upsert_template(session, data)
    return success_response(template)


@router.post("/send", status_code=status.HTTP_201_CREATED)
async def send_notification(
    data: NotificationCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    service: NotificationService = SERVICE,
) -> dict:
    notification = await service.create_and_send(session, data, source="api")
    return success_response(notification)


@router.get("/templates/{template_key}")
async def get_template(
    template_key: str,
    session: AsyncSession = Depends(get_session),
    service: NotificationService = SERVICE,
) -> dict:
    template = await service.render_template(session, template_key, None)
    if template is None:
        raise NotFoundError(f"Template '{template_key}' not found")
    return success_response(template)


@router.get("/health")
async def health(request: Request) -> dict:
    return success_response({"status": "ok", "service": "notification-service"})