"""Database models for the configuration-service.

Tables are named in snake_case and inherit audit fields per DATABASE_STANDARDS.md.
"""

from ehos_common.db import AuditMixin, Base
from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column


class FeatureFlag(Base, AuditMixin):
    """A boolean feature flag enabling or disabling a capability."""

    __tablename__ = "feature_flags"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class ConfigurationEntry(Base, AuditMixin):
    """A versioned key/value reference configuration entry."""

    __tablename__ = "configuration_entries"

    config_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    config_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    value_type: Mapped[str] = mapped_column(String(50), nullable=False, default="string")
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
