"""Database entities for the analytics-service."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class DepartmentMetric(Base):
    """Current KPI snapshot for one department metric."""

    __tablename__ = "department_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)  # currency|percent|count|minutes|days
    delta_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    good_when: Mapped[str] = mapped_column(String(10), nullable=False, default="up")  # up|down
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="ok")  # ok|warn|alert
    hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MetricPoint(Base):
    """One daily history point for a department metric series."""

    __tablename__ = "metric_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)


class LocalizationOverride(Base):
    """Optional per-country overrides managed by administrators."""

    __tablename__ = "localization_overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, unique=True, index=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    locale_tag: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange_rate: Mapped[float] = mapped_column(Float, nullable=False)  # per 1 unit of base currency
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SeedState(Base):
    """Tracks whether the realistic demo/ops dataset has been seeded."""

    __tablename__ = "seed_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seed_key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    seeded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
