"""Database models for the audit-service.

Audit records are immutable: no UPDATE or DELETE operations are permitted.
Records are written once with a SHA-256 content hash chained to the previous
record so tampering is detectable.
"""

from datetime import UTC, datetime
from hashlib import sha256

from ehos_common.db import Base
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class AuditRecord(Base):
    __tablename__ = "audit_records"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    def compute_hash(self) -> str:
        """Chain-safe hash over the full logical content of the record."""
        occurred = self.occurred_at
        if isinstance(occurred, datetime):
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=UTC)
            canonical_occurred = occurred.astimezone(UTC).isoformat()
        else:
            canonical_occurred = str(occurred)
        canonical = "|".join(
            str(v)
            for v in [
                self.event_id,
                self.event_type,
                self.actor_id,
                self.correlation_id,
                self.source,
                self.ip_address,
                self.action,
                self.resource_type,
                self.resource_id,
                self.old_value,
                self.new_value,
                self.reason,
                canonical_occurred,
            ]
        )
        base = (self.previous_hash or "") + canonical
        return sha256(base.encode("utf-8")).hexdigest()