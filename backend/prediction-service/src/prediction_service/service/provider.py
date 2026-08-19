"""PredictionService: forecast lifecycle for the nine advisory targets.

Implements the P2-P5 pipeline in-process and offline:
  train (P2) -> evaluate + register (P3) -> approve -> serve/supersede (P4)
  -> reconcile / drift (P5).

Forecast rows are append-only (``predictions.status`` VALID -> SUPERSEDED) and
every generated forecast publishes ``PredictionGenerated`` on the event bus so
agents (Inventory/HR/Pharmacy/Executive) and dashboards can react. Forecasts are
advisory: nothing here triggers automatic reorders, roster or spend changes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ehos_common import KafkaProducer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prediction_service.configuration import PredictionSettings
from prediction_service.dto import schemas as dto
from prediction_service.entity import models as ent
from prediction_service.service import forecast as fc


class PredictionError(Exception):
    """Application error carrying an API status code."""

    def __init__(self, error_code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code


def _entity_uuid(entity_type: str, entity_id: str) -> uuid.UUID:
    """Coerce a logical entity id to a stable UUID (keeps ai_db's UUID column)."""
    try:
        return uuid.UUID(entity_id)
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid5(uuid.NAMESPACE_DNS, f"ehos:{entity_type}:{entity_id}")


class PredictionService:
    """Owns all forecast operations."""

    def __init__(self, settings: PredictionSettings):
        self.settings = settings

    # --- catalog -------------------------------------------------------------

    def list_targets(self) -> list[dict]:
        return [
            {
                "key": t.key,
                "entity_type": t.entity_type,
                "horizon": t.horizon,
                "metric": t.metric,
                "gate": t.gate,
                "description": t.description,
            }
            for t in fc.FORECAST_TARGETS.values()
        ]

    # --- training (P2 + P3) ----------------------------------------------------

    async def train(self, session: AsyncSession, payload: dto.TrainModelIn) -> dict:
        target = fc.FORECAST_TARGETS.get(payload.target)
        if target is None:
            raise PredictionError("UNKNOWN_TARGET", f"unknown forecast target '{payload.target}'", 404)
        if payload.adapter not in fc.ALLOWED_ADAPTERS:
            raise PredictionError("UNKNOWN_ADAPTER", f"unknown adapter '{payload.adapter}'", 400)
        if not payload.series:
            raise PredictionError("EMPTY_SERIES", "training series must not be empty", 400)

        prediction_key = payload.prediction_key or f"{payload.entity_type}.{payload.horizon}"
        version = payload.version or await self._next_version(session, prediction_key)
        steps = payload.holdout or self.settings.default_horizon_steps
        result = fc.backtest(payload.series, steps, payload.adapter, payload.period, target.metric)
        invert = target.metric == "PRECISION"
        verdict, note = fc.verdict_for(result["value"], target.gate, invert=invert)

        model = ent.AiModel(
            model_key=f"{prediction_key}.{version}",
            family="PREDICTION",
            base_name=payload.adapter,
            model_version=version,
            purpose=f"{target.key} forecast ({payload.entity_type})",
            training_source=payload.dataset_ref or "in-memory series",
            artifact_ref=f"adapter:{payload.adapter}:period:{payload.period}",
            approval_status="APPROVED" if payload.approve and verdict == "PASS" else "REVIEW",
            approved_at=datetime.now(UTC) if payload.approve and verdict == "PASS" else None,
            attributes={
                "target": target.key,
                "entity_type": payload.entity_type,
                "horizon": target.horizon,
                "metric": result,
                "gate": target.gate,
                "verdict": verdict,
                "adapter": payload.adapter,
                "period": payload.period,
            },
        )
        session.add(model)
        await session.flush()
        session.add(
            ent.ModelEvaluation(
                model_id=model.id,
                dataset_ref=payload.dataset_ref,
                metrics=result,
                verdict=verdict,
                notes=note,
            )
        )
        await session.flush()
        return {
            "model": _model_out(model),
            "evaluation": {
                "id": str(model.id),
                "verdict": verdict,
                "metrics": result,
                "notes": note,
                "gate": target.gate,
            },
        }

    async def _next_version(self, session: AsyncSession, prediction_key: str) -> str:
        prefix = f"{prediction_key}."
        count = (
            await session.execute(
                select(func.count()).select_from(ent.AiModel).where(
                    ent.AiModel.model_key.like(f"{prefix}%"),
                    ent.AiModel.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        return f"v{int(count) + 1}"

    async def list_models(
        self, session: AsyncSession, family: str = "PREDICTION", approved_only: bool = False
    ) -> list[dict]:
        stmt = select(ent.AiModel).where(
            ent.AiModel.deleted_at.is_(None), ent.AiModel.family == family
        )
        if approved_only:
            stmt = stmt.where(ent.AiModel.approval_status == "APPROVED")
        stmt = stmt.order_by(ent.AiModel.created_at.desc())
        rows = (await session.execute(stmt)).scalars().all()
        return [_model_out(m) for m in rows]

    async def get_model(self, session: AsyncSession, model_key: str) -> dict:
        model = await self._find_model(session, model_key)
        return _model_out(model)

    async def approve_model(self, session: AsyncSession, model_key: str, payload: dto.ApproveModelIn) -> dict:
        model = await self._find_model(session, model_key)
        if model.approval_status == "REJECTED":
            raise PredictionError("MODEL_REJECTED", "model is rejected and cannot be approved", 409)
        if model.approval_status == "DEPRECATED":
            raise PredictionError("MODEL_DEPRECATED", "model is deprecated and cannot be approved", 409)
        model.approval_status = "APPROVED"
        model.approved_by = _entity_uuid("user", payload.approver_id) if payload.approver_id else None
        model.approved_at = datetime.now(UTC)
        await session.flush()
        return _model_out(model)

    async def reject_model(self, session: AsyncSession, model_key: str, payload: dto.ApproveModelIn) -> dict:
        model = await self._find_model(session, model_key)
        model.approval_status = "REJECTED"
        model.approved_by = _entity_uuid("user", payload.approver_id) if payload.approver_id else None
        await session.flush()
        return _model_out(model)

    async def _find_model(self, session: AsyncSession, model_key: str) -> ent.AiModel:
        row = (
            await session.execute(
                select(ent.AiModel).where(
                    ent.AiModel.model_key == model_key, ent.AiModel.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise PredictionError("MODEL_NOT_FOUND", f"model '{model_key}' not found", 404)
        return row

    # --- serving (P4) ----------------------------------------------------------

    async def generate(
        self,
        session: AsyncSession,
        payload: dto.PredictionIn,
        producer: KafkaProducer | None = None,
    ) -> dict:
        prediction_key = payload.prediction_key or f"{payload.entity_type}.{payload.horizon}"
        steps = payload.horizon_steps or self.settings.default_horizon_steps
        if steps < 1:
            raise PredictionError("BAD_HORIZON", "horizon_steps must be >= 1", 400)
        if not payload.series:
            raise PredictionError("EMPTY_SERIES", "history series must not be empty", 400)

        model, model_version = await self._serving_model(session, prediction_key)
        result = fc.forecast_series(
            payload.series, steps, payload.adapter or self.settings.default_adapter, payload.period
        )
        confidence = float(model.attributes.get("confidence", 0.9)) if model else self.settings.default_confidence
        window_from, window_to = self._window(payload.window_from, payload.series, steps)

        entity_id = _entity_uuid(payload.entity_type, payload.entity_id) if payload.entity_id else None

        await self._supersede(session, prediction_key, window_from)
        row = ent.Prediction(
            prediction_key=prediction_key,
            entity_type=payload.entity_type,
            entity_id=entity_id,
            horizon=payload.horizon,
            window_from=window_from,
            window_to=window_to,
            model_id=model.id if model else None,
            forecast=result,
            confidence=round(confidence, 4),
            status="VALID",
        )
        session.add(row)
        await session.flush()

        outcome = _serving_out(row, model_version, result)
        # Publish only after the served row commits (outbox) to avoid phantom
        # events when the DB write fails; fall back to immediate publish for
        # direct calls.
        await publish_generated(producer, outcome, session.info.get("outbox"))
        return outcome

    async def _serving_model(
        self, session: AsyncSession, prediction_key: str
    ) -> tuple[ent.AiModel | None, str]:
        """Best approved model for the key, or a built-in fallback."""
        rows = (
            await session.execute(
                select(ent.AiModel)
                .where(
                    ent.AiModel.family == "PREDICTION",
                    ent.AiModel.approval_status == "APPROVED",
                    ent.AiModel.model_key.like(f"{prediction_key}.%"),
                    ent.AiModel.deleted_at.is_(None),
                )
                .order_by(ent.AiModel.created_at.desc())
            )
        ).scalars().all()
        if rows:
            return rows[0], rows[0].model_version
        return None, "builtin.seasonal_naive"

    async def _supersede(self, session: AsyncSession, prediction_key: str, window_from: date) -> int:
        rows = (
            await session.execute(
                select(ent.Prediction).where(
                    ent.Prediction.prediction_key == prediction_key,
                    ent.Prediction.window_from == window_from,
                    ent.Prediction.status == "VALID",
                    ent.Prediction.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for row in rows:
            row.status = "SUPERSEDED"
        await session.flush()
        return len(rows)

    @staticmethod
    def _window(window_from: date | None, history: list[float], steps: int) -> tuple[date, date]:
        if window_from is None:
            window_from = date.today() + timedelta(days=1)
        window_to = window_from + timedelta(days=steps - 1)
        return window_from, window_to

    async def latest(self, session: AsyncSession, prediction_key: str, window_from: date | None = None) -> dict:
        stmt = select(ent.Prediction).where(
            ent.Prediction.prediction_key == prediction_key,
            ent.Prediction.status == "VALID",
            ent.Prediction.deleted_at.is_(None),
        )
        if window_from is not None:
            stmt = stmt.where(ent.Prediction.window_from == window_from)
        row = (await session.execute(stmt.order_by(ent.Prediction.created_at.desc()))).scalars().first()
        if row is None:
            raise PredictionError("PREDICTION_NOT_FOUND", f"no valid prediction for '{prediction_key}'", 404)
        return _serving_out(row, _model_version_for(row), row.forecast)

    async def list_predictions(
        self, session: AsyncSession, prediction_key: str | None, status: str | None, limit: int, offset: int
    ) -> dict:
        stmt = select(ent.Prediction).where(ent.Prediction.deleted_at.is_(None))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        if prediction_key:
            stmt = stmt.where(ent.Prediction.prediction_key == prediction_key)
            count_stmt = select(func.count()).select_from(
                select(ent.Prediction)
                .where(ent.Prediction.deleted_at.is_(None), ent.Prediction.prediction_key == prediction_key)
                .subquery()
            )
        if status:
            stmt = stmt.where(ent.Prediction.status == status)
            count_stmt = select(func.count()).select_from(
                select(ent.Prediction)
                .where(ent.Prediction.deleted_at.is_(None), ent.Prediction.status == status)
                .subquery()
            )
        total = (await session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(ent.Prediction.created_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()
        return {
            "items": [_serving_out(r, _model_version_for(r), r.forecast) for r in rows],
            "total": total,
        }

    # --- monitoring (P5) --------------------------------------------------------

    async def reconcile(
        self, session: AsyncSession, payload: dto.ReconcileIn
    ) -> dict:
        """Compare actuals against the latest VALID forecast; flag stale models."""
        row = (
            await session.execute(
                select(ent.Prediction)
                .where(
                    ent.Prediction.prediction_key == payload.prediction_key,
                    ent.Prediction.status == "VALID",
                    ent.Prediction.deleted_at.is_(None),
                )
                .order_by(ent.Prediction.created_at.desc())
            )
        ).scalars().first()
        if row is None:
            raise PredictionError("PREDICTION_NOT_FOUND", f"no valid prediction for '{payload.prediction_key}'", 404)

        actuals = payload.series[: len(row.forecast["value"])]
        predicted = row.forecast["value"][: len(payload.series)]
        metric = fc.wape(actuals, predicted)
        model_metrics: dict[str, Any] = {}

        retrain = False
        reason = "forecast error within tolerance"
        verdict = "PASS"
        if row.model_id is not None and metric > 0.20:
            model = (
                await session.execute(select(ent.AiModel).where(ent.AiModel.id == row.model_id))
            ).scalar_one_or_none()
            if model is not None and model.approval_status == "APPROVED":
                model.approval_status = "DEPRECATED"
                model.approved_at = None
                model_metrics = {
                    "drift_wape": round(metric, 6),
                    "actuals_window": len(actuals),
                    "prediction_window": len(predicted),
                }
                session.add(
                    ent.ModelEvaluation(
                        model_id=model.id,
                        dataset_ref=f"reconcile:{payload.prediction_key}",
                        metrics=model_metrics,
                        verdict="FAIL",
                        notes="actual-vs-forecast drift beyond gate; retrain proposed",
                    )
                )
                retrain = True
                reason = "forecast drifted beyond gate; model flagged DEPRECATED"
                verdict = "FAIL"

        return {
            "prediction_key": payload.prediction_key,
            "metric": "WAPE",
            "wape": round(metric, 6),
            "verdict": verdict,
            "retrain_proposed": retrain,
            "reason": reason,
            "window_from": row.window_from.isoformat() if row.window_from else None,
            "model_metrics": model_metrics or None,
        }


def _model_out(model: ent.AiModel) -> dict:
    return {
        "id": str(model.id),
        "model_key": model.model_key,
        "family": model.family,
        "base_name": model.base_name,
        "version": model.model_version,
        "purpose": model.purpose,
        "artifact_ref": model.artifact_ref,
        "approval_status": model.approval_status,
        "approved_at": model.approved_at,
        "attributes": model.attributes,
        "created_at": model.created_at,
    }


def _model_version_for(row: ent.Prediction) -> str:
    return f"v{row.version}" if row.model_id else "builtin.seasonal_naive"


def _serving_out(row: ent.Prediction, model_version: str, result: dict) -> dict:
    return {
        "prediction_key": row.prediction_key,
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id) if row.entity_id else None,
        "horizon": row.horizon,
        "window_from": row.window_from.isoformat() if row.window_from else None,
        "window_to": row.window_to.isoformat() if row.window_to else None,
        "forecast": result,
        "confidence": float(row.confidence) if row.confidence is not None else None,
        "model_version": model_version,
        "generated_at": row.created_at.isoformat(),
        "sources": [f"feature:{row.prediction_key}:history"],
    }


async def publish_generated(producer: KafkaProducer | None, outcome: dict, outbox=None) -> None:
    """Publish a PredictionGenerated event (best-effort; never breaks serving).

    Stages on the request outbox (published after commit) when wired, otherwise
    publishes immediately.
    """
    from datetime import UTC

    from ehos_common import DomainEvent, EventRegistry

    registry = EventRegistry()
    event = DomainEvent(
        event_type="PredictionGenerated",
        source="prediction-service",
        payload={
            "predictionKey": outcome["prediction_key"],
            "entityType": outcome["entity_type"] or "",
            "entityId": outcome["entity_id"] or "",
            "horizon": outcome["horizon"],
            "generatedAt": datetime.now(UTC).isoformat(),
        },
    )
    try:
        envelope = event.envelope()
        registry.validate(envelope)
        topic = registry.topic("PredictionGenerated")
        if outbox is not None:
            outbox.add_envelope(topic, envelope)
        elif producer is not None:
            await producer.publish_envelope(topic, envelope)
    except Exception:  # noqa: BLE001 - eventing is best-effort
        import logging

        logging.getLogger("prediction_service.events").exception("failed to publish PredictionGenerated")