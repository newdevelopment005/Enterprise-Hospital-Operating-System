import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from ehos_common.db import Base
from sqlalchemy import (
    JSON,
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Item(Base):
    __tablename__ = "items"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    sku: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String, nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    reorder_point: Mapped[int] = mapped_column(default=0, nullable=False)
    reorder_qty: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    stock_items: Mapped[list["StockItem"]] = relationship("StockItem", back_populates="item", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("sku", name="uq_items_sku"),
        Index("idx_items_category", "category"),
    )


class StockItem(Base):
    __tablename__ = "stock_items"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    item_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("items.id"), nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    lot_number: Mapped[str | None] = mapped_column(String)
    expiry_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    quantity_on_hand: Mapped[int] = mapped_column(default=0, nullable=False)
    quantity_reserved: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    item: Mapped["Item"] = relationship("Item", back_populates="stock_items", lazy="selectin")
    movements: Mapped[list["StockMovement"]] = relationship("StockMovement", back_populates="stock_item", lazy="selectin")

    __table_args__ = (
        CheckConstraint("quantity_on_hand >= 0", name="ck_stock_qty_nonneg"),
        UniqueConstraint("item_id", "location", "lot_number", name="uq_stock_item_loc_lot"),
        Index("idx_stock_items_item", "item_id"),
        Index("idx_stock_items_location", "location"),
        Index("idx_stock_items_expiry", "expiry_date"),
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    stock_item_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stock_items.id"), nullable=False)
    movement_type: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String)
    reference_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)
    performed_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    stock_item: Mapped["StockItem"] = relationship("StockItem", back_populates="movements", lazy="selectin")

    __table_args__ = (
        CheckConstraint(
            "movement_type IN ('RECEIPT','DISPENSE','TRANSFER','ADJUSTMENT','WRITE_OFF','RETURN')",
            name="ck_movement_type",
        ),
        Index("idx_movements_stock", "stock_item_id"),
        Index("idx_movements_type", "movement_type"),
        Index("idx_movements_performed", "performed_at"),
    )


class ReorderAlert(Base):
    __tablename__ = "reorder_alerts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    item_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("items.id"), nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    quantity_on_hand: Mapped[int] = mapped_column(nullable=False)
    reorder_point: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String, default="OPEN", nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("idx_reorder_item", "item_id"),
        Index("idx_reorder_location", "location"),
        Index("idx_reorder_status", "status"),
    )
