"""REST API for the prediction-service.

Standard EHOS envelope {"success": true, "data": ...}. Forecasts are advisory;
no endpoint mutates operational state outside ``predictions`` lifecycle rows.
"""

from __future__ import annotations

from datetime import date

from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from prediction_service.dto import schemas as dto
from prediction_service.service import provider as svc

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        outbox = Outbox()
        session.info["outbox"] = outbox
        try:
            yield session
            await session.commit()
            # Publish staged events after the write is durable; discard on rollback.
            await outbox.flush(getattr(request.app.state, "producer", None))
        except Exception:
            await session.rollback()
            outbox.discard()
            raise


def _s(request: Request) -> svc.PredictionService:
    return request.app.state.prediction_service


def _producer(request: Request):
    return getattr(request.app.state, "producer", None)


def _ok(data, status_code: int = 200) -> dict:
    return {"success": True, "data": data, "statusCode": status_code}


# --- catalog & model registry ---------------------------------------------------


@router.get("/targets")
async def list_targets(request: Request):
    return _ok(_s(request).list_targets())


@router.post("/models/train", status_code=status.HTTP_201_CREATED)
async def train_model(
    payload: dto.TrainModelIn, request: Request, session: AsyncSession = Depends(get_session)
):
    return _ok(await _s(request).train(session, payload), status.HTTP_201_CREATED)


@router.get("/models")
async def list_models(
    request: Request,
    session: AsyncSession = Depends(get_session),
    approved_only: bool = Query(default=False),
):
    return _ok(await _s(request).list_models(session, approved_only=approved_only))


@router.get("/models/{model_key}")
async def get_model(model_key: str, request: Request, session: AsyncSession = Depends(get_session)):
    return _ok(await _s(request).get_model(session, model_key))


@router.post("/models/{model_key}/approve")
async def approve_model(
    model_key: str, payload: dto.ApproveModelIn, request: Request, session: AsyncSession = Depends(get_session)
):
    return _ok(await _s(request).approve_model(session, model_key, payload))


@router.post("/models/{model_key}/reject")
async def reject_model(
    model_key: str, payload: dto.ApproveModelIn, request: Request, session: AsyncSession = Depends(get_session)
):
    return _ok(await _s(request).reject_model(session, model_key, payload))


# --- serving ---------------------------------------------------------------------


@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate(
    payload: dto.PredictionIn, request: Request, session: AsyncSession = Depends(get_session)
):
    return _ok(await _s(request).generate(session, payload, _producer(request)), status.HTTP_201_CREATED)


@router.get("/lookup/{prediction_key}")
async def lookup(
    prediction_key: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    window_from: date | None = None,
):
    return _ok(await _s(request).latest(session, prediction_key, window_from))


@router.get("")
async def list_predictions(
    request: Request,
    session: AsyncSession = Depends(get_session),
    prediction_key: str | None = None,
    prediction_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _ok(
        await _s(request).list_predictions(session, prediction_key, prediction_status, limit, offset)
    )


# --- monitoring (P5) ---------------------------------------------------------------


@router.post("/reconcile")
async def reconcile(
    payload: dto.ReconcileIn, request: Request, session: AsyncSession = Depends(get_session)
):
    return _ok(await _s(request).reconcile(session, payload))