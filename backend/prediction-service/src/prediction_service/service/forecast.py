"""Forecast catalog, adapters and validation metrics for the prediction-service.

Everything is pure Python / offline: the two local adapters are *seasonal-naive*
(period --- basic seasonal baselining) and *ses* (single exponential smoothing).
Forecasts are advisory only and always returned with an interval band and a
human-readable confidence label (PREDICTIVE_ANALYTICS_ARCHITECTURE §2, §5, §10).
"""

from __future__ import annotations

from dataclasses import dataclass

# --- forecast catalog ---------------------------------------------------------
#
# The nine advisory targets. ``gate`` is the status-gate metric threshold from
# PREDICTIVE_ANALYTICS_ARCHITECTURE §5 (e.g. WAPE < 20% for patient inflow @7d).


@dataclass(frozen=True)
class ForecastTarget:
    key: str
    entity_type: str
    horizon: str
    metric: str
    gate: float
    description: str


FORECAST_TARGETS: dict[str, ForecastTarget] = {
    "patient-inflow": ForecastTarget(
        key="patient-inflow", entity_type="department", horizon="7d", metric="WAPE", gate=0.20,
        description="Patient inflow per department (daily · 7/30d)",
    ),
    "emergency-demand": ForecastTarget(
        key="emergency-demand", entity_type="emergency", horizon="24h", metric="WAPE", gate=0.25,
        description="Emergency department demand (hourly · 24-72h)",
    ),
    "medicine-usage": ForecastTarget(
        key="medicine-usage", entity_type="medication", horizon="30d", metric="WAPE", gate=0.20,
        description="Medicine usage per medication item (daily · 30d)",
    ),
    "bed-occupancy": ForecastTarget(
        key="bed-occupancy", entity_type="ward", horizon="7d", metric="MAPE", gate=0.15,
        description="Bed occupancy per ward (daily · 7d)",
    ),
    "icu-load": ForecastTarget(
        key="icu-load", entity_type="icu-unit", horizon="7d", metric="MAPE", gate=0.15,
        description="ICU load per unit (daily · 7d)",
    ),
    "staffing": ForecastTarget(
        key="staffing", entity_type="department", horizon="weekly", metric="MAE", gate=0.10,
        description="Staff requirement per department/role (shift · weekly)",
    ),
    "revenue": ForecastTarget(
        key="revenue", entity_type="biller", horizon="monthly", metric="WAPE", gate=0.15,
        description="Revenue per charge/biller (monthly)",
    ),
    "inventory-shortage": ForecastTarget(
        key="inventory-shortage", entity_type="item", horizon="7d", metric="PRECISION", gate=0.60,
        description="Inventory shortage risk per item (7/30 day)",
    ),
    "equipment-maintenance": ForecastTarget(
        key="equipment-maintenance", entity_type="asset", horizon="days", metric="MAE", gate=3.0,
        description="Equipment maintenance days-to-event (days)",
    ),
}

ALLOWED_ADAPTERS = ("seasonal_naive", "ses")


# --- adapters -----------------------------------------------------------------


def seasonal_naive_forecast(history: list[float], steps: int, period: int) -> list[float]:
    """Repeat the most recent ``period``-seasonal pattern plus a linear drift."""
    if not history:
        return []
    period = max(1, int(period))
    n = len(history)
    drift = 0.0
    if n > 1:
        drift = (history[-1] - history[0]) / (n - 1)
    out: list[float] = []
    for k in range(1, steps + 1):
        base = history[max(0, n - period + (k - 1) % period)] if period > 0 else history[-1]
        out.append(base + drift * k)
    return out


def ses_forecast(history: list[float], steps: int, alpha: float = 0.3) -> list[float]:
    """Single exponential smoothing: level = alpha*x + (1-alpha)*level."""
    if not history:
        return []
    level = history[0]
    for value in history[1:]:
        level = alpha * value + (1 - alpha) * level
    return [level] * steps


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def interval_bands(history: list[float], steps: int) -> tuple[list[float], list[float]]:
    """q10/q90 bands from the residual standard deviation (expanding with steps)."""
    sigma = _std(history)
    q10 = []
    q90 = []
    for k in range(1, steps + 1):
        width = 1.28 * sigma * (1 + k * 0.1)
        q10.append(-width)
        q90.append(width)
    return q10, q90


def forecast_series(history: list[float], steps: int, adapter: str, period: int) -> dict:
    """Compute point forecast + q10/q90 offsets for the requested horizon."""
    values = ses_forecast(history, steps) if adapter == "ses" else seasonal_naive_forecast(history, steps, period)
    q10_off, q90_off = interval_bands(history, steps)
    q10 = [v + lo for v, lo in zip(values, q10_off, strict=False)]
    q90 = [v + hi for v, hi in zip(values, q90_off, strict=False)]
    return {
        "value": values,
        "q10": [max(0.0, v) for v in q10],
        "q90": [max(0.0, v) for v in q90],
    }


# --- metrics ------------------------------------------------------------------


def mean_absolute_error(actuals: list[float], predicted: list[float]) -> float:
    if not actuals:
        return 0.0
    return sum(abs(a - p) for a, p in zip(actuals, predicted, strict=False)) / len(actuals)


def wape(actuals: list[float], predicted: list[float]) -> float:
    """Weighted absolute percentage error (scaled by the true magnitude)."""
    total = sum(abs(a) for a in actuals)
    if total <= 0:
        return 0.0
    return sum(abs(a - p) for a, p in zip(actuals, predicted, strict=False)) / total


def mape(actuals: list[float], predicted: list[float]) -> float:
    values = [abs(a - p) / a if a else 0.0 for a, p in zip(actuals, predicted, strict=False)]
    return sum(values) / len(values) if values else 0.0


def evaluate(actuals: list[float], predicted: list[float], metric: str) -> dict:
    if metric == "MAPE":
        value = mape(actuals, predicted)
    elif metric == "PRECISION":
        value = _precision_at_k(actuals, predicted)
    else:
        value = wape(actuals, predicted)
    return {
        "metric": metric,
        "value": round(value, 6),
        "mae": round(mean_absolute_error(actuals, predicted), 6),
        "horizon": len(actuals),
    }


def _precision_at_k(actuals: list[float], predicted: list[float]) -> float:
    """Fraction of flagged (predicted high-risk) steps that were real risk steps."""
    if not predicted:
        return 0.0
    k = len(predicted)
    threshold = max(actuals) if actuals else 0.0
    predicted_flagged = [p > threshold for p in predicted]
    if not any(predicted_flagged):
        return 0.0
    actual_flagged = [a > threshold for a in actuals]
    hits = sum(1 for i in range(k) if predicted_flagged[i] and actual_flagged[i])
    return hits / sum(predicted_flagged)


def backtest(history: list[float], steps: int, adapter: str, period: int, metric: str) -> dict:
    """Hold-out evaluation: fit on history[:-steps], score on the last ``steps``."""
    if len(history) <= steps:
        steps = max(1, len(history) // 2)
    train = history[:-steps]
    actuals = history[-steps:]
    if adapter == "seasonal_naive":
        predicted = seasonal_naive_forecast(train, steps, period)
    else:
        predicted = ses_forecast(train, steps)
    return evaluate(actuals, predicted, metric)


def verdict_for(metric_value: float, gate: float, invert: bool = False) -> tuple[str, str]:
    """Map measured metric to the §5 status gate (PASS/WARN/FAIL)."""
    worse = metric_value > gate if not invert else metric_value < gate
    if not worse:
        return "PASS", "within status gate"
    if (not invert and metric_value <= gate * 1.5) or (invert and metric_value >= 0.5 * gate):
        return "WARN", "approaching status gate - owner sign-off required"
    return "FAIL", "outside status gate - retrain proposed"