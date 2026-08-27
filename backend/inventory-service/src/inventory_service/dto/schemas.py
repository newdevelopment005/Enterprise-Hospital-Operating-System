from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---- Item ----


class ItemBase(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    unit_of_measure: str = Field(min_length=1, max_length=32)
    unit_cost: Decimal | None = None
    reorder_point: int = 0
    reorder_qty: int = 0
    is_active: bool = True


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    unit_of_measure: str | None = Field(default=None, min_length=1, max_length=32)
    unit_cost: Decimal | None = None
    reorder_point: int | None = None
    reorder_qty: int | None = None
    is_active: bool | None = None


class ItemRead(ItemBase):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---- StockItem ----


class StockItemBase(BaseModel):
    item_id: UUID
    location: str = Field(min_length=1, max_length=128)
    lot_number: str | None = Field(default=None, max_length=64)
    expiry_date: datetime | None = None


class StockItemCreate(StockItemBase):
    quantity_on_hand: int = 0


class StockItemRead(StockItemBase):
    id: UUID
    quantity_on_hand: int
    quantity_reserved: int
    status: str
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---- StockMovement ----


class StockMovementBase(BaseModel):
    stock_item_id: UUID
    movement_type: str = Field(pattern="^(RECEIPT|DISPENSE|TRANSFER|ADJUSTMENT|WRITE_OFF|RETURN)$")
    quantity: int = Field(ge=1)
    reference_type: str | None = Field(default=None, max_length=64)
    reference_id: UUID | None = None
    reason: str | None = None


class StockMovementCreate(StockMovementBase):
    performed_by: UUID


class StockMovementRead(StockMovementBase):
    id: UUID
    performed_by: UUID
    performed_at: datetime
    status: str
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---- ReorderAlert ----


class ReorderAlertRead(BaseModel):
    id: UUID
    item_id: UUID
    location: str
    quantity_on_hand: int
    reorder_point: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---- Pagination ----


class PaginatedResponse(BaseModel):
    items: list
    total: int
    limit: int
    offset: int
