"""REST API for the analytics-service.

Standard EHOS envelope {"success": true, "data": ...}. Read-only executive
metrics; the country/currency/timezone is resolved per request.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.service import localization as loc
from analytics_service.service import provider as svc

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _s(request: Request) -> svc.AnalyticsService:
    return request.app.state.analytics_service


def _ok(data, status_code: int = 200) -> dict:
    return {"success": True, "data": data, "statusCode": status_code}


def _headers(request: Request) -> dict[str, str]:
    return {k.lower(): v for k, v in request.headers.items()}


def _profile(request: Request, country: str | None) -> loc.CountryProfile:
    settings = request.app.state.settings
    code = country
    if not code and settings.country_resolution == "auto":
        code = loc.detect_country(
            query_country=None,
            headers=_headers(request),
            default_country=settings.default_country_code,
        )
    if not code:
        code = settings.default_country_code
    return loc.profile_for(code)


@router.get("/locale")
async def get_locale(request: Request, country: str | None = Query(default=None)):
    """Resolve (predict) the country and return currency/timezone info."""
    profile = _profile(request, country)
    payload = loc.locale_payload(profile)
    payload["resolution"] = (
        "explicit" if country else request.app.state.settings.country_resolution
    )
    return _ok(payload)


@router.get("/overview")
async def overview(
    request: Request,
    country: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Executive dashboard payload: KPIs, series and per-department breakdowns."""
    profile = _profile(request, country)
    return _ok(await _s(request).overview(session, profile))


@router.get("/departments/{code}")
async def department(
    code: str,
    request: Request,
    country: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """One department's KPI snapshot (finance, hr, operations, ...)."""
    profile = _profile(request, country)
    return _ok(await _s(request).department(session, code, profile))
