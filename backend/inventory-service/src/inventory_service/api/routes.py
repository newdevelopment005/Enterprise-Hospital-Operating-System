import uuid
from uuid import UUID

from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from inventory_service.dto.schemas import (
    ItemCreate,
    ItemRead,
    ItemUpdate,
    PaginatedResponse,
    ReorderAlertRead,
    StockItemCreate,
    StockItemRead,
    StockMovementCreate,
    StockMovementRead,
)
from inventory_service.service.inventory_service import InventoryError, service

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        outbox = Outbox()
        session.info["outbox"] = outbox
        try:
            yield session
            await session.commit()
            # Publish staged events only after the write is durable; events
            # staged for a rolled-back transaction are discarded so no phantom
            # events are emitted when the DB commit fails.
            await outbox.flush(getattr(request.app.state, "producer", None))
        except Exception:
            await session.rollback()
            outbox.discard()
            raise


def get_actor(request: Request) -> UUID | None:
    raw = request.headers.get("X-User-Id")
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


# ---- Items ----

@router.post("/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_item(db, payload, actor_id)
    except InventoryError as e:
        raise HTTPException(status_code=409 if e.code == "DUPLICATE_SKU" else 400, detail=e.message)


@router.get("/items/{item_id}", response_model=ItemRead)
async def get_item(item_id: UUID, db: AsyncSession = Depends(get_session)):
    item = await service.get_item(db, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@router.get("/items", response_model=PaginatedResponse)
async def list_items(category: str | None = None, active_only: bool = True, limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session)):
    items = await service.list_items(db, category, active_only, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/items/{item_id}", response_model=ItemRead)
async def update_item(item_id: UUID, payload: ItemUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_item(db, item_id, payload, actor_id)
    except InventoryError as e:
        raise HTTPException(status_code=404 if e.code == "ITEM_NOT_FOUND" else 400, detail=e.message)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_item(item_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        await service.deactivate_item(db, item_id, actor_id)
    except InventoryError as e:
        raise HTTPException(status_code=404 if e.code == "ITEM_NOT_FOUND" else 400, detail=e.message)


# ---- Stock Items ----

@router.post("/stock", response_model=StockItemRead, status_code=status.HTTP_201_CREATED)
async def create_stock_item(payload: StockItemCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_stock_item(db, payload, actor_id)
    except InventoryError as e:
        raise HTTPException(status_code=409 if e.code == "DUPLICATE_STOCK" else 400, detail=e.message)


@router.get("/stock/{stock_id}", response_model=StockItemRead)
async def get_stock_item(stock_id: UUID, db: AsyncSession = Depends(get_session)):
    stock = await service.get_stock_item(db, stock_id)
    if not stock:
        raise HTTPException(404, "Stock item not found")
    return stock


@router.get("/stock", response_model=PaginatedResponse)
async def list_stock_items(item_id: UUID | None = None, location: str | None = None, limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session)):
    items = await service.list_stock_items(db, item_id, location, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


# ---- Movements ----

@router.post("/stock/{stock_id}/receive", response_model=StockMovementRead, status_code=status.HTTP_201_CREATED)
async def receive_stock(stock_id: UUID, payload: StockMovementCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.receive_stock(db, stock_id, payload.quantity, actor_id, payload.reason, payload.reference_type, payload.reference_id)
    except InventoryError as e:
        raise HTTPException(status_code=404 if e.code == "STOCK_NOT_FOUND" else 400, detail=e.message)


@router.post("/stock/{stock_id}/dispense", response_model=StockMovementRead, status_code=status.HTTP_201_CREATED)
async def dispense_stock(stock_id: UUID, payload: StockMovementCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.dispense_stock(db, stock_id, payload.quantity, actor_id, payload.reason, payload.reference_type, payload.reference_id)
    except InventoryError as e:
        raise HTTPException(status_code=404 if e.code == "STOCK_NOT_FOUND" else 400, detail=e.message)


@router.post("/stock/{stock_id}/adjust", response_model=StockMovementRead, status_code=status.HTTP_201_CREATED)
async def adjust_stock(stock_id: UUID, quantity: int, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor), reason: str | None = None):
    try:
        return await service.adjust_stock(db, stock_id, quantity, actor_id, reason)
    except InventoryError as e:
        raise HTTPException(status_code=404 if e.code == "STOCK_NOT_FOUND" else 400, detail=e.message)


@router.get("/movements", response_model=PaginatedResponse)
async def list_movements(stock_item_id: UUID | None = None, movement_type: str | None = None, limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session)):
    items = await service.list_movements(db, stock_item_id, movement_type, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


# ---- Reorder Alerts ----

@router.get("/reorder-alerts", response_model=PaginatedResponse)
async def list_reorder_alerts(status_filter: str | None = Query(None, alias="status"), limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session)):
    items = await service.list_reorder_alerts(db, status_filter, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.post("/reorder-alerts/{alert_id}/resolve", response_model=ReorderAlertRead)
async def resolve_alert(alert_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.resolve_alert(db, alert_id, actor_id)
    except InventoryError as e:
        raise HTTPException(status_code=404 if e.code == "ALERT_NOT_FOUND" else 400, detail=e.message)


# ---- Expiring Stock ----

@router.get("/expiring", response_model=list[StockItemRead])
async def expiring_soon(within_days: int = Query(30, le=365), location: str | None = None, db: AsyncSession = Depends(get_session)):
    return await service.expiring_soon(db, within_days, location)
