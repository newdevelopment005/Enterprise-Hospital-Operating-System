"""AnalyticsService: realistic multi-department hospital metrics.

Seeds a deterministic, clinically plausible dataset on first start (finance &
accounts, HR, inpatient operations, outpatient/ED, pharmacy & inventory,
laboratory) and serves executive-dashboard-shaped KPI + series payloads with
currency conversion applied for the resolved country.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.configuration import AnalyticsSettings
from analytics_service.entity import models as ent
from analytics_service.service.localization import CountryProfile, convert, locale_payload

HISTORY_DAYS = 30


def _mulberry32(seed: int):
    state = seed

    def next_float() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = (t + (t << 10)) & 0xFFFFFFFF
        t = (t ^ (t >> 6)) & 0xFFFFFFFF
        t = (t + (t << 3)) & 0xFFFFFFFF
        t = (t ^ (t >> 11)) & 0xFFFFFFFF
        t = (t + (t << 15)) & 0xFFFFFFFF
        return t / 0xFFFFFFFF

    return next_float


# --- department metric catalogue (base-currency values) --------------------------

BEDS = 420

# department, key, label, unit, good_when, base_value_fn(day_index), hint
def _revenue(d: int) -> float:
    weekly = 1.0 + 0.12 * math.sin(2 * math.pi * d / 7)
    growth = 1.0 + 0.004 * d
    return 168_000.0 * weekly * growth


def _expenses(d: int) -> float:
    weekly = 1.0 + 0.05 * math.sin(2 * math.pi * (d + 2) / 7)
    return 141_000.0 * weekly


METRIC_CATALOGUE: list[dict] = [
    # --- Finance & Accounts ---
    {"department": "FINANCE", "key": "daily_revenue", "label": "Daily revenue", "unit": "currency",
     "good_when": "up", "series": _revenue,
     "hint": "All billable streams: consultations, pharmacy, lab, radiology, ward."},
    {"department": "FINANCE", "key": "daily_expenses", "label": "Daily operating expenses", "unit": "currency",
     "good_when": "down", "series": _expenses, "hint": "Salaries, supplies, utilities, maintenance."},
    {"department": "FINANCE", "key": "receivables", "label": "Outstanding receivables", "unit": "currency",
     "good_when": "down", "value": 1_240_000.0, "drift": -0.003,
     "hint": "Unpaid invoices >30 days included; collection team is working the aging queue."},
    {"department": "FINANCE", "key": "claims_pending", "label": "Insurance claims pending", "unit": "count",
     "good_when": "down", "value": 318.0, "drift": -0.002,
     "hint": "Submitted to insurers, awaiting adjudication."},
    {"department": "FINANCE", "key": "collection_rate", "label": "Collection rate", "unit": "percent",
     "good_when": "up", "value": 87.4, "drift": 0.0008,
     "hint": "Collected vs billed within 60 days."},
    # --- Human Resources ---
    {"department": "HR", "key": "headcount", "label": "Total headcount", "unit": "count",
     "good_when": "up", "value": 1264.0, "drift": 0.0004,
     "hint": "All contracted staff across clinical and non-clinical departments."},
    {"department": "HR", "key": "on_duty", "label": "On duty now", "unit": "count",
     "good_when": "up", "value": 387.0, "oscillation": True,
     "hint": "Shift-rostered staff currently on site."},
    {"department": "HR", "key": "attendance_rate", "label": "Attendance rate", "unit": "percent",
     "good_when": "up", "value": 94.2, "drift": 0.0005,
     "hint": "Scheduled shifts actually worked over trailing 7 days."},
    {"department": "HR", "key": "overtime_hours", "label": "Overtime hours / week", "unit": "count",
     "good_when": "down", "value": 942.0, "drift": 0.004,
     "hint": "Sustained overtime signals understaffing risk."},
    {"department": "HR", "key": "open_positions", "label": "Open positions", "unit": "count",
     "good_when": "down", "value": 37.0, "drift": -0.003,
     "hint": "Approved requisitions not yet filled."},
    {"department": "HR", "key": "monthly_payroll", "label": "Monthly payroll cost", "unit": "currency",
     "good_when": "down", "value": 2_180_000.0, "drift": 0.001,
     "hint": "Gross salaries plus statutory contributions."},
    {"department": "HR", "key": "staff_utilization", "label": "Staff utilisation", "unit": "percent",
     "good_when": "down", "value": 84.6, "drift": 0.0008,
     "hint": "Productive hours vs rostered hours; burnout watch beyond 97%."},
    # --- Inpatient Operations ---
    {"department": "OPERATIONS", "key": "admissions_today", "label": "Admissions today", "unit": "count",
     "good_when": "up", "value": 46.0, "oscillation": True,
     "hint": "Inpatient admissions registered since midnight."},
    {"department": "OPERATIONS", "key": "discharges_today", "label": "Discharges today", "unit": "count",
     "good_when": "up", "value": 41.0, "oscillation": True,
     "hint": "Completed discharge workflows today."},
    {"department": "OPERATIONS", "key": "bed_occupancy", "label": "Bed occupancy", "unit": "percent",
     "good_when": "down", "value": 86.4, "drift": 0.0012,
     "hint": f"{BEDS} staffed beds; surge threshold at 93%."},
    {"department": "OPERATIONS", "key": "avg_los", "label": "Average length of stay", "unit": "days",
     "good_when": "down", "value": 4.3, "drift": -0.001,
     "hint": "Mean days from admission to discharge, trailing 7 days."},
    {"department": "OPERATIONS", "key": "surgeries_today", "label": "Surgeries today", "unit": "count",
     "good_when": "up", "value": 18.0, "oscillation": True,
     "hint": "Elective and emergency theatre cases."},
    {"department": "OPERATIONS", "key": "mortality_rate", "label": "Mortality rate", "unit": "percent",
     "good_when": "down", "value": 1.4, "drift": 0.0,
     "hint": "In-hospital deaths per admissions, trailing 7 days."},
    {"department": "OPERATIONS", "key": "readmission_30d", "label": "30-day readmission", "unit": "percent",
     "good_when": "down", "value": 10.8, "drift": -0.0005,
     "hint": "Unplanned readmissions within 30 days of discharge."},
    # --- Outpatient / Emergency ---
    {"department": "OUTPATIENT", "key": "ed_visits", "label": "ED visits today", "unit": "count",
     "good_when": "up", "value": 152.0, "oscillation": True,
     "hint": "Emergency department registrations."},
    {"department": "OUTPATIENT", "key": "waiting_time", "label": "ED waiting time", "unit": "minutes",
     "good_when": "down", "value": 38.0, "oscillation": True,
     "hint": "Median door-to-triage; alert beyond 60 minutes."},
    {"department": "OUTPATIENT", "key": "appointments", "label": "Appointments today", "unit": "count",
     "good_when": "up", "value": 486.0, "oscillation": True,
     "hint": "Scheduled clinic appointments across specialties."},
    {"department": "OUTPATIENT", "key": "no_show_rate", "label": "No-show rate", "unit": "percent",
     "good_when": "down", "value": 9.6, "drift": -0.001,
     "hint": "Booked patients who did not attend, trailing 7 days."},
    # --- Pharmacy & Inventory ---
    {"department": "PHARMACY", "key": "stock_readiness", "label": "Stock readiness", "unit": "percent",
     "good_when": "up", "value": 82.5, "drift": 0.001,
     "hint": "Share of essential medicine list fully stocked."},
    {"department": "PHARMACY", "key": "below_reorder", "label": "Items below reorder point", "unit": "count",
     "good_when": "down", "value": 64.0, "drift": -0.002,
     "hint": "SKUs at or under reorder level across stores."},
    {"department": "PHARMACY", "key": "expiring_30d", "label": "Batches expiring ≤30d", "unit": "count",
     "good_when": "down", "value": 88.0, "drift": 0.0,
     "hint": "Pharmacy batches requiring FEFO dispatch first."},
    {"department": "PHARMACY", "key": "procurement_pending", "label": "Purchase orders pending", "unit": "count",
     "good_when": "down", "value": 23.0, "drift": -0.004,
     "hint": "POs awaiting supplier confirmation or goods receipt."},
    # --- Laboratory ---
    {"department": "LABORATORY", "key": "tests_today", "label": "Lab tests today", "unit": "count",
     "good_when": "up", "value": 974.0, "oscillation": True,
     "hint": "Haematology, chemistry, micro and molecular panels."},
    {"department": "LABORATORY", "key": "turnaround_time", "label": "Median turnaround", "unit": "minutes",
     "good_when": "down", "value": 74.0, "drift": -0.001,
     "hint": "Order-to-result median across routine panels."},
]

SERIES_SLUGS = {
    "revenue": ("FINANCE", "daily_revenue", "Revenue", "currency"),
    "expenses": ("FINANCE", "daily_expenses", "Expenses", "currency"),
    "admissions": ("OPERATIONS", "admissions_today", "Admissions", "count"),
    "discharges": ("OPERATIONS", "discharges_today", "Discharges", "count"),
    "occupancy": ("OPERATIONS", "bed_occupancy", "Bed occupancy", "percent"),
    "utilization": ("HR", "staff_utilization", "Staff utilisation", "percent"),
    "waiting": ("OUTPATIENT", "waiting_time", "Waiting time", "minutes"),
    "attendance": ("HR", "attendance_rate", "Staff attendance", "percent"),
    "inventory": ("PHARMACY", "stock_readiness", "Stock readiness", "percent"),
    "mortality": ("OPERATIONS", "mortality_rate", "Mortality", "percent"),
    "readmission": ("OPERATIONS", "readmission_30d", "30-day readmission", "percent"),
}

# Dashboard KPI slugs mirror the executive dashboard's canonical keys so the
# live payload is a drop-in replacement for the demo dataset.
DASHBOARD_KPI_SLUGS: list[tuple[str, str, str]] = [
    ("OPERATIONS", "admissions_today", "admissions"),
    ("OPERATIONS", "discharges_today", "discharges"),
    ("FINANCE", "daily_revenue", "revenue"),
    ("FINANCE", "daily_expenses", "expenses"),
    ("OPERATIONS", "bed_occupancy", "occupancy"),
    ("OUTPATIENT", "waiting_time", "waiting"),
    ("HR", "staff_utilization", "utilization"),
    ("PHARMACY", "stock_readiness", "inventory"),
    ("OPERATIONS", "mortality_rate", "mortality"),
    ("OPERATIONS", "readmission_30d", "readmission"),
]

DEPARTMENT_NAMES = {
    "FINANCE": "Finance & Accounts",
    "HR": "Human Resources",
    "OPERATIONS": "Inpatient Operations",
    "OUTPATIENT": "Outpatient & Emergency",
    "PHARMACY": "Pharmacy & Inventory",
    "LABORATORY": "Laboratory",
}


class AnalyticsError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AnalyticsService:
    """Serves executive KPIs and localizes them per detected country."""

    def __init__(self, settings: AnalyticsSettings):
        self.settings = settings

    # --- seeding -----------------------------------------------------------------

    async def ensure_seeded(self, session: AsyncSession) -> None:
        already = (
            await session.execute(select(ent.SeedState).where(ent.SeedState.seed_key == "ops_v1"))
        ).scalar_one_or_none()
        if already is not None:
            return
        rng = _mulberry32(20260821)
        today = datetime.now(UTC).date()
        for spec in METRIC_CATALOGUE:
            base = spec.get("value")
            series_fn = spec.get("series")
            drift = spec.get("drift", 0.0)
            oscillation = spec.get("oscillation", False)
            values: list[float] = []
            for day_index in range(HISTORY_DAYS):
                if series_fn is not None:
                    value = series_fn(day_index) * (1.0 + rng() * 0.06 - 0.03)
                elif oscillation:
                    wave = 1.0 + 0.22 * math.sin(2 * math.pi * day_index / 7)
                    value = base * wave * (1.0 + rng() * 0.12 - 0.06) + drift * base * day_index
                else:
                    value = base * (1.0 + drift * day_index) * (1.0 + rng() * 0.04 - 0.02)
                values.append(max(value, 0.0))
            current, prior = values[-1], values[-2]
            delta_pct = ((current - prior) / prior * 100.0) if prior else 0.0
            session.add(
                ent.DepartmentMetric(
                    department=spec["department"],
                    metric_key=spec["key"],
                    label=spec["label"],
                    value=round(current, 2),
                    unit=spec["unit"],
                    delta_pct=round(delta_pct, 2),
                    good_when=spec["good_when"],
                    status=self._status(spec["key"], current),
                    hint=spec.get("hint"),
                )
            )
            for offset, value in enumerate(values):
                session.add(
                    ent.MetricPoint(
                        department=spec["department"],
                        metric_key=spec["key"],
                        day=today - timedelta(days=HISTORY_DAYS - 1 - offset),
                        value=round(value, 2),
                    )
                )
        session.add(ent.SeedState(seed_key="ops_v1"))
        await session.flush()

    @staticmethod
    def _status(metric_key: str, value: float) -> str:
        thresholds = {
            "bed_occupancy": (88.0, 93.0, "up"),
            "waiting_time": (45.0, 60.0, "up"),
            "overtime_hours": (900.0, 1100.0, "up"),
            "no_show_rate": (12.0, 18.0, "up"),
            "below_reorder": (80.0, 120.0, "up"),
            "stock_readiness": (70.0, 55.0, "down"),
            "collection_rate": (85.0, 75.0, "down"),
        }
        cfg = thresholds.get(metric_key)
        if cfg is None:
            return "ok"
        warn_at, alert_at, higher_is_bad = cfg
        if higher_is_bad:
            if value >= alert_at:
                return "alert"
            if value >= warn_at:
                return "warn"
        else:
            if value <= alert_at:
                return "alert"
            if value <= warn_at:
                return "warn"
        return "ok"

    # --- serving -----------------------------------------------------------------

    async def overview(self, session: AsyncSession, profile: CountryProfile) -> dict:
        await self.ensure_seeded(session)
        metrics = (
            (await session.execute(select(ent.DepartmentMetric))).scalars().all()
        )
        all_points = (
            (
                await session.execute(
                    select(ent.MetricPoint).order_by(ent.MetricPoint.day)
                )
            )
            .scalars()
            .all()
        )

        by_key = {(m.department, m.metric_key): m for m in metrics}
        history: dict[tuple[str, str], list[float]] = {}
        for p in all_points:
            history.setdefault((p.department, p.metric_key), []).append(p.value)

        kpis = []
        for dept, metric_key, slug in DASHBOARD_KPI_SLUGS:
            metric = by_key.get((dept, metric_key))
            if metric is not None:
                kpis.append(self._kpi_payload(metric, profile, history.get((dept, metric_key), []), slug=slug))
        series = {
            slug: self._series_payload(slug, label, unit, history.get((dept, key), []), profile)
            for slug, (dept, key, label, unit) in SERIES_SLUGS.items()
        }

        departments: dict[str, dict] = {}
        for m in metrics:
            dept = departments.setdefault(
                m.department,
                {"code": m.department, "name": DEPARTMENT_NAMES.get(m.department, m.department.title()), "kpis": []},
            )
            dept["kpis"].append(self._kpi_payload(m, profile, history.get((m.department, m.metric_key), [])))
        return {
            "source": "analytics-service",
            "locale": locale_payload(profile),
            "kpis": kpis,
            "series": series,
            "departments": sorted(departments.values(), key=lambda d: d["code"]),
            "generatedAt": datetime.now(UTC).isoformat(),
        }

    async def department(self, session: AsyncSession, code: str, profile: CountryProfile) -> dict:
        await self.ensure_seeded(session)
        rows = (
            (await session.execute(select(ent.DepartmentMetric).where(ent.DepartmentMetric.department == code.upper())))
            .scalars()
            .all()
        )
        if not rows:
            raise AnalyticsError(f"unknown department '{code}'", 404)
        return {
            "code": code.upper(),
            "name": DEPARTMENT_NAMES.get(code.upper(), code.title()),
            "kpis": [self._kpi_payload(m, profile, []) for m in rows],
            "locale": locale_payload(profile),
        }

    @staticmethod
    def _dashboard_kpi_keys() -> list[tuple[str, str]]:
        return [(dept, key) for dept, key, _ in DASHBOARD_KPI_SLUGS]

    def _kpi_payload(
        self, m: ent.DepartmentMetric, profile: CountryProfile, history: list[float], slug: str | None = None
    ) -> dict:
        value = convert(m.value, profile) if m.unit == "currency" else m.value
        spark = (history[-12:] or [m.value] * 12)
        return {
            "key": slug or m.metric_key,
            "department": m.department,
            "label": m.label,
            "value": round(value, 2),
            "format": self._format(m.unit),
            "deltaPct": m.delta_pct,
            "goodWhen": m.good_when,
            "status": m.status,
            "hint": m.hint or "",
            "spark": [round(v, 2) for v in spark],
            "asOf": m.captured_at.isoformat() if m.captured_at else datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _format(unit: str) -> str:
        mapping = {"currency": "currency", "percent": "percent", "minutes": "minutes", "days": "number"}
        return mapping.get(unit, "number")

    def _series_payload(
        self,
        slug: str,
        label: str,
        unit: str,
        values: list[float],
        profile: CountryProfile,
    ) -> dict:
        color = {
            "revenue": "#2e7d32", "expenses": "#c62828", "admissions": "#1565c0",
            "discharges": "#00838f", "occupancy": "#6a1b9a", "utilization": "#4527a0",
            "waiting": "#ef6c00", "attendance": "#2e7d32", "inventory": "#f9a825",
            "mortality": "#b71c1c", "readmission": "#e65100",
        }.get(slug, "#455a64")
        today = datetime.now(UTC).date()
        start = today - timedelta(days=max(len(values), 1) - 1)
        return {
            "key": slug,
            "label": label,
            "unit": unit,
            "color": color,
            "points": [
                {
                    "t": (start + timedelta(days=i)).isoformat(),
                    "v": round(convert(v, profile) if unit == "currency" else v, 2),
                }
                for i, v in enumerate(values[-HISTORY_DAYS:])
            ],
        }

    async def total_points(self, session: AsyncSession) -> int:
        return (
            await session.execute(select(func.count()).select_from(ent.MetricPoint))
        ).scalar_one()
