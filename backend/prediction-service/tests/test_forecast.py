"""Tests for the forecast engine (adapters, metrics, backtest, verdicts)."""

import pytest

from prediction_service.service import forecast as fc


def test_seasonal_naive_keeps_shape_and_seasonality():
    history = [10.0, 12.0, 11.0, 13.0] * 3
    out = fc.seasonal_naive_forecast(history, 4, period=4)
    assert len(out) == 4
    drift = (history[-1] - history[0]) / (len(history) - 1)
    assert out[0] == pytest.approx(history[-4] + drift)
    assert out[2] == pytest.approx(history[-2] + 3 * drift)
    assert out[3] == pytest.approx(history[-1] + 4 * drift)


def test_ses_flat_when_flat_history():
    out = fc.ses_forecast([5.0, 5.0, 5.0], 3)
    assert out == [5.0, 5.0, 5.0]


def test_forecast_series_returns_bands():
    history = [10.0, 12.0, 11.0, 13.0, 10.0, 12.0, 11.0, 13.0]
    result = fc.forecast_series(history, 4, "seasonal_naive", 4)
    assert set(result) == {"value", "q10", "q90"}
    assert len(result["value"]) == len(result["q10"]) == len(result["q90"]) == 4
    assert all(lo <= v <= hi for v, lo, hi in zip(result["value"], result["q10"], result["q90"], strict=False))


def test_metrics_perfect_fit_is_zero():
    actuals = [10.0, 12.0, 11.0]
    assert fc.mean_absolute_error(actuals, actuals) == 0.0
    assert fc.wape(actuals, actuals) == 0.0
    assert fc.mape(actuals, actuals) == 0.0


def test_backtest_uses_time_ordered_holdout():
    history = list(range(1, 21))
    result = fc.backtest(history, 5, "seasonal_naive", 5, "WAPE")
    assert result["horizon"] == 5
    assert result["metric"] == "WAPE"
    assert 0 <= result["value"] <= 1


def test_verdict_gates():
    verdict, _ = fc.verdict_for(0.10, 0.20)
    assert verdict == "PASS"
    verdict, _ = fc.verdict_for(0.19, 0.20)
    assert verdict == "PASS"
    verdict, _ = fc.verdict_for(0.29, 0.20)
    assert verdict == "WARN"
    verdict, _ = fc.verdict_for(0.50, 0.20)
    assert verdict == "FAIL"
    verdict, _ = fc.verdict_for(0.70, 0.60, invert=True)
    assert verdict == "PASS"