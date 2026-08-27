"""Tests for the multi-department metrics provider."""

from sqlalchemy import select

from analytics_service.entity import models as ent
from analytics_service.service.localization import COUNTRY_PROFILES


async def test_seed_is_idempotent(session, service):
    await service.ensure_seeded(session)
    await service.ensure_seeded(session)
    rows = (await session.execute(select(ent.DepartmentMetric))).scalars().all()
    points = (await session.execute(select(ent.MetricPoint))).scalars().all()
    assert len(rows) > 0
    assert len(points) == len(rows) * 30  # 30 days of history per metric


async def test_overview_covers_all_departments(session, service):
    data = await service.overview(session, COUNTRY_PROFILES["EG"])
    codes = {d["code"] for d in data["departments"]}
    assert {"FINANCE", "HR", "OPERATIONS", "OUTPATIENT", "PHARMACY", "LABORATORY"} <= codes
    keys = {k["key"] for k in data["kpis"]}
    assert {"revenue", "expenses", "admissions", "discharges", "occupancy", "waiting",
            "utilization", "inventory", "mortality", "readmission"} == keys
    for slug in ("revenue", "expenses", "admissions", "discharges", "occupancy", "waiting",
                 "utilization", "mortality", "readmission"):
        assert len(data["series"][slug]["points"]) == 30


async def test_currency_conversion_applied_in_overview(session, service):
    usd = await service.overview(session, COUNTRY_PROFILES["US"])
    egp = await service.overview(session, COUNTRY_PROFILES["EG"])
    revenue_usd = next(k for k in usd["kpis"] if k["key"] == "revenue")["value"]
    revenue_egp = next(k for k in egp["kpis"] if k["key"] == "revenue")["value"]
    assert abs(revenue_egp / revenue_usd - COUNTRY_PROFILES["EG"].exchange_rate) < 0.01
    # Non-currency KPIs are never converted.
    occ_usd = next(k for k in usd["kpis"] if k["key"] == "occupancy")["value"]
    occ_egp = next(k for k in egp["kpis"] if k["key"] == "occupancy")["value"]
    assert occ_usd == occ_egp


async def test_department_endpoint(session, service):
    hr = await service.department(session, "hr", COUNTRY_PROFILES["US"])
    assert hr["code"] == "HR"
    keys = {k["key"] for k in hr["kpis"]}
    assert {"headcount", "on_duty", "monthly_payroll"} <= keys


async def test_unknown_department_raises(session, service):
    from analytics_service.service.provider import AnalyticsError

    try:
        await service.department(session, "NOPE", COUNTRY_PROFILES["US"])
    except AnalyticsError as err:
        assert err.status_code == 404
    else:
        raise AssertionError("expected AnalyticsError")
