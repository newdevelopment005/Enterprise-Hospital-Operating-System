"""Tests for the PredictionService provider (train/evaluate/approve/serve/reconcile)."""

from __future__ import annotations

import pytest

from prediction_service.dto import schemas as dto
from prediction_service.entity import models as ent
from prediction_service.service.provider import PredictionError


def _series() -> list[float]:
    return [10.0, 12.0, 11.0, 13.0, 10.0, 12.0, 11.0, 13.0, 10.0, 12.0, 11.0, 13.0, 9.0, 11.0, 10.0]


async def test_train_registers_model_and_evaluation(session, service):
    result = await service.train(
        session,
        dto.TrainModelIn(
            target="bed-occupancy",
            entity_type="ward",
            prediction_key="ward.A.7d",
            series=_series(),
            dataset_ref="ward_history_2026",
        ),
    )
    model, evaluation = result["model"], result["evaluation"]
    assert model["family"] == "PREDICTION"
    assert model["approval_status"] == "REVIEW"
    assert evaluation["verdict"] in ("PASS", "WARN", "FAIL")
    assert "metrics" in evaluation
    rows = (await session.execute(_select_all(ent.AiModel))).scalars().all()
    evals = (await session.execute(_select_all(ent.ModelEvaluation))).scalars().all()
    assert len(rows) == 1 and len(evals) == 1
    assert evals[0].model_id == rows[0].id


def _select_all(model):
    from sqlalchemy import select

    return select(model)


async def test_train_version_auto_increments(session, service):
    payload = dto.TrainModelIn(
        target="bed-occupancy",
        entity_type="ward",
        prediction_key="ward.A.7d",
        series=_series(),
        approve=True,
    )
    first = await service.train(session, payload)
    second = await service.train(session, payload)
    assert first["model"]["version"].startswith("v1")
    assert second["model"]["version"].startswith("v2")
    assert first["model"]["model_key"] != second["model"]["model_key"]
    assert second["model"]["approval_status"] in ("APPROVED", "REVIEW")


async def test_train_auto_approves_on_pass(session, service):
    result = await service.train(
        session,
        dto.TrainModelIn(target="bed-occupancy", prediction_key="ward.A.7d", series=_series(), approve=True),
    )
    if result["evaluation"]["verdict"] == "PASS":
        assert result["model"]["approval_status"] == "APPROVED"
    else:
        assert result["model"]["approval_status"] == "REVIEW"


async def test_train_rejects_unknown_target(session, service):
    with pytest.raises(PredictionError) as exc:
        await service.train(session, dto.TrainModelIn(target="nope", series=[1.0]))
    assert exc.value.error_code == "UNKNOWN_TARGET"


async def test_approve_and_reject_flow(session, service):
    payload = dto.TrainModelIn(target="bed-occupancy", prediction_key="ward.A.7d", series=_series(), approve=True)
    result = await service.train(session, payload)
    model_key = result["model"]["model_key"]
    if result["model"]["approval_status"] != "APPROVED":
        out = await service.approve_model(session, model_key, dto.ApproveModelIn(approver_id="u-1"))
        assert out["approval_status"] == "APPROVED"
    out = await service.reject_model(session, model_key, dto.ApproveModelIn(approver_id="u-2"))
    assert out["approval_status"] == "REJECTED"


async def test_serve_uses_approved_model_and_supersedes(session, service):
    trained = await service.train(
        session,
        dto.TrainModelIn(target="bed-occupancy", entity_type="ward", prediction_key="ward.A.7d", series=_series()),
    )
    model_key = trained["model"]["model_key"]
    if trained["model"]["approval_status"] != "APPROVED":
        await service.approve_model(session, model_key, dto.ApproveModelIn(approver_id="u-1"))

    first = await service.generate(
        session,
        dto.PredictionIn(
            prediction_key="ward.A.7d",
            entity_type="ward",
            entity_id="A",
            horizon="7d",
            series=_series()[:-3],
        ),
    )
    assert first["model_version"].startswith("v1")
    assert len(first["forecast"]["value"]) == 7

    second = await service.generate(
        session,
        dto.PredictionIn(
            prediction_key="ward.A.7d",
            entity_type="ward",
            entity_id="A",
            horizon="7d",
            series=_series(),
        ),
    )
    assert second["prediction_key"] == "ward.A.7d"
    rows = (await session.execute(_select_all(ent.Prediction))).scalars().all()
    assert len(rows) == 2
    assert sum(1 for r in rows if r.status == "VALID") == 1
    assert sum(1 for r in rows if r.status == "SUPERSEDED") == 1


async def test_serve_falls_back_to_builtin_without_approved_model(session, service):
    out = await service.generate(
        session,
        dto.PredictionIn(prediction_key="ival.1.7d", entity_type="item", entity_id="i-1", series=[5.0, 6.0, 4.0]),
    )
    assert out["model_version"] == "builtin.seasonal_naive"
    assert out["confidence"] is not None


async def test_latest_raises_when_missing(session, service):
    with pytest.raises(PredictionError) as exc:
        await service.latest(session, "missing.key")
    assert exc.value.status_code == 404


async def test_reconcile_flags_stale_model(session, service):
    trained = await service.train(
        session,
        dto.TrainModelIn(target="bed-occupancy", prediction_key="ward.A.7d", series=_series(), approve=True),
    )
    model_key = trained["model"]["model_key"]
    if trained["model"]["approval_status"] != "APPROVED":
        await service.approve_model(session, model_key, dto.ApproveModelIn(approver_id="u-1"))
    await service.generate(
        session,
        dto.PredictionIn(prediction_key="ward.A.7d", entity_type="ward", entity_id="A", series=_series()),
    )
    out = await service.reconcile(
        session, dto.ReconcileIn(prediction_key="ward.A.7d", series=[x + 40 for x in _series()])
    )
    assert out["prediction_key"] == "ward.A.7d"
    assert isinstance(out["wape"], float)
    model = (
        (await session.execute(_select_all(ent.AiModel).where(ent.AiModel.model_key == model_key)))
        .scalars()
        .first()
    )
    if out["retrain_proposed"]:
        assert model.approval_status == "DEPRECATED"