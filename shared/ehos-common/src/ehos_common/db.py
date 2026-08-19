"""Async SQLAlchemy session helper and audit-field base model.

Database standards per CODING_STANDARDS.md section 9-10:

- Every table has primary key, ``created_at``, ``updated_at``, ``created_by``, ``updated_by``.
- Databases are never shared between services (one database per service).
- Clinical data is never hard-deleted; they support version history and audit.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base carrying audit fields."""


class AuditMixin:
    """Common audit columns required on every table."""

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(nullable=True)
    updated_by: Mapped[str | None] = mapped_column(nullable=True)


class Database:
    """Owns the engine and session factory for a single service database."""

    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init_models(self, base: type[DeclarativeBase]) -> None:
        """Create tables from metadata (development convenience).

        Production migrations are applied via Alembic, never via ``create_all``.
        """
        async with self.engine.begin() as connection:
            await connection.run_sync(base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()

    def session(self) -> AsyncSession:
        return self.session_factory()


async def get_session(database: Database):
    """FastAPI dependency yielding a session with commit on success."""
    async with database.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise