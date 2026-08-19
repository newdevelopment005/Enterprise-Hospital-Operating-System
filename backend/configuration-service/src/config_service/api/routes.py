"""REST API for the configuration-service.

Endpoints are versioned under ``/api/v1`` and return the standard envelope
defined in EHSO API_DESIGN_STANDARD.md.
"""

from collections.abc import AsyncIterator

from ehos_common.api import ConflictError, NotFoundError, success_response
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from config_service.dto.schemas import (
    ConfigurationEntryIn,
    FeatureFlagIn,
    ReferenceConfigAllOut,
)
from config_service.service.configuration_service import ConfigurationService

router = APIRouter(prefix="/api/v1", tags=["configuration"])


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_service(request: Request) -> ConfigurationService:
    return request.app.state.configuration_service


SERVICE = Depends(get_service)


@router.post("/flags", status_code=status.HTTP_201_CREATED)
async def create_flag(
    data: FeatureFlagIn,
    session: AsyncSession = Depends(get_session),
    service: ConfigurationService = SERVICE,
) -> dict:
    flag = await service.create_flag(session, data, updated_by=None)
    return success_response(flag)


@router.get("/flags")
async def list_flags(
    session: AsyncSession = Depends(get_session),
    service: ConfigurationService = SERVICE,
) -> dict:
    return success_response(await service.list_flags(session))


@router.patch("/flags/{name}")
async def set_flag(
    name: str,
    enabled: bool,
    session: AsyncSession = Depends(get_session),
    service: ConfigurationService = SERVICE,
) -> dict:
    flag = await service.set_flag(session, name, enabled, updated_by=None)
    if flag is None:
        raise NotFoundError(f"Feature flag '{name}' not found")
    return success_response(flag)


@router.put("/entries/{config_key}")
async def upsert_entry(
    config_key: str,
    data: ConfigurationEntryIn,
    session: AsyncSession = Depends(get_session),
    service: ConfigurationService = SERVICE,
) -> dict:
    if data.config_key != config_key:
        raise ConflictError("Key in body must match the URL path key")
    entry = await service.upsert_entry(session, data, updated_by=None)
    return success_response(entry)


@router.get("/entries")
async def list_entries(
    session: AsyncSession = Depends(get_session),
    service: ConfigurationService = SERVICE,
) -> dict:
    return success_response(await service.list_entries(session))


@router.get("/entries/{config_key}")
async def get_entry(
    config_key: str,
    session: AsyncSession = Depends(get_session),
    service: ConfigurationService = SERVICE,
) -> dict:
    entry = await service.get_entry(session, config_key)
    if entry is None:
        raise NotFoundError(f"Configuration '{config_key}' not found")
    return success_response(entry)


@router.get("/all")
async def get_all_reference_config(
    session: AsyncSession = Depends(get_session),
    service: ConfigurationService = SERVICE,
) -> dict:
    """Aggregate snapshot intended for service bootstrap and feature flags."""
    return success_response(
        ReferenceConfigAllOut(
            flags={f.name: f.enabled for f in await service.list_flags(session)},
            entries={e.config_key: e.config_value for e in await service.list_entries(session)},
        )
    )