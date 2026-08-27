from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from ehos_common.events import DomainEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inventory_service.dto.schemas import (
    ItemCreate,
    ItemUpdate,
    StockItemCreate,
    StockMovementCreate,
)
from inventory_service.entity.models import Item, ReorderAlert, StockItem, StockMovement

TOPICS = {
    "ItemCreated": "inventory.item.created",
    "ItemUpdated": "inventory.item.updated",
    "StockReceived": "inventory.stock.received",
    "StockDispensed": "inventory.stock.dispensed",
    "StockAdjusted": "inventory.stock.adjusted",
    "ReorderAlert": "inventory.reorder.alert",
}


class InventoryError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class InventoryService:
    """Inventory service: items, stock, movements, reorder alerts."""

    def __init__(self, producer: object | None = None):
        self.producer = producer

    async def _publish(self, session: AsyncSession, event_type: str, payload: dict) -> None:
        if self.producer is None:
            return
        try:
            topic = TOPICS.get(event_type)
            if topic is None:
                return
            event = DomainEvent(
                event_type=event_type,
                source="inventory-service",
                user_id=None,
                payload={"occurredAt": datetime.now(UTC).isoformat(), **payload},
            )
            outbox = session.info.get("outbox")
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await self.producer.publish(topic, event)
        except Exception:
            pass

    # ------------------------ Item Catalog ------------------------

    async def create_item(self, session: AsyncSession, payload: ItemCreate, actor_id: UUID) -> Item:
        existing = await session.execute(select(Item).where(Item.sku == payload.sku, Item.deleted_at.is_(None)))
        if existing.scalars().first():
            raise InventoryError("DUPLICATE_SKU", f"SKU '{payload.sku}' already exists")

        item = Item(
            sku=payload.sku,
            name=payload.name,
            category=payload.category,
            unit_of_measure=payload.unit_of_measure,
            unit_cost=payload.unit_cost,
            reorder_point=payload.reorder_point,
            reorder_qty=payload.reorder_qty,
            is_active=payload.is_active,
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(item)
        await session.flush()
        await self._publish(session, "ItemCreated", {"sku": item.sku, "name": item.name})
        return item

    async def get_item(self, session: AsyncSession, item_id: UUID) -> Item | None:
        return await session.get(Item, item_id)

    async def list_items(self, session: AsyncSession, category: str | None = None, active_only: bool = True, limit: int = 50, offset: int = 0) -> list[Item]:
        stmt = select(Item).where(Item.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(Item.is_active.is_(True))
        if category:
            stmt = stmt.where(Item.category == category)
        stmt = stmt.order_by(Item.name).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_item(self, session: AsyncSession, item_id: UUID, payload: ItemUpdate, actor_id: UUID) -> Item:
        item = await self.get_item(session, item_id)
        if not item:
            raise InventoryError("ITEM_NOT_FOUND", "Item not found")
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(item, k, v)
        item.updated_by = actor_id
        item.version += 1
        await self._publish(session, "ItemUpdated", {"item_id": str(item.id), **data})
        return item

    async def deactivate_item(self, session: AsyncSession, item_id: UUID, actor_id: UUID) -> Item:
        item = await self.get_item(session, item_id)
        if not item:
            raise InventoryError("ITEM_NOT_FOUND", "Item not found")
        item.is_active = False
        item.deleted_at = datetime.utcnow()
        item.deleted_by = actor_id
        item.deletion_reason = "deactivated"
        item.updated_by = actor_id
        item.version += 1
        return item

    # ------------------------ Stock Items ------------------------

    async def create_stock_item(self, session: AsyncSession, payload: StockItemCreate, actor_id: UUID) -> StockItem:
        item = await self.get_item(session, payload.item_id)
        if not item:
            raise InventoryError("ITEM_NOT_FOUND", "Item not found")

        existing = await session.execute(
            select(StockItem).where(
                StockItem.item_id == payload.item_id, StockItem.location == payload.location,
                StockItem.lot_number == payload.lot_number, StockItem.deleted_at.is_(None),
            )
        )
        if existing.scalars().first():
            raise InventoryError("DUPLICATE_STOCK", "Stock item already exists for this location/lot")

        stock = StockItem(
            item_id=payload.item_id,
            location=payload.location,
            lot_number=payload.lot_number,
            expiry_date=payload.expiry_date,
            quantity_on_hand=payload.quantity_on_hand,
            quantity_reserved=0,
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(stock)
        await session.flush()
        return stock

    async def get_stock_item(self, session: AsyncSession, stock_id: UUID) -> StockItem | None:
        return await session.get(StockItem, stock_id)

    async def list_stock_items(self, session: AsyncSession, item_id: UUID | None = None, location: str | None = None, limit: int = 50, offset: int = 0) -> list[StockItem]:
        stmt = select(StockItem).where(StockItem.deleted_at.is_(None))
        if item_id:
            stmt = stmt.where(StockItem.item_id == item_id)
        if location:
            stmt = stmt.where(StockItem.location == location)
        stmt = stmt.order_by(StockItem.location).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------ Movements ------------------------

    async def receive_stock(self, session: AsyncSession, stock_id: UUID, quantity: int, actor_id: UUID, reason: str | None = None, ref_type: str | None = None, ref_id: UUID | None = None) -> StockMovement:
        stock = await session.get(StockItem, stock_id)
        if not stock:
            raise InventoryError("STOCK_NOT_FOUND", "Stock item not found")

        stock.quantity_on_hand += quantity
        stock.updated_by = actor_id
        stock.version += 1

        movement = StockMovement(
            stock_item_id=stock_id,
            movement_type="RECEIPT",
            quantity=quantity,
            reference_type=ref_type,
            reference_id=ref_id,
            reason=reason,
            performed_by=actor_id,
            status="COMPLETED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(movement)
        await session.flush()

        await self._publish(session, "StockReceived", {"stock_id": str(stock_id), "quantity": quantity, "location": stock.location})
        return movement

    async def dispense_stock(self, session: AsyncSession, stock_id: UUID, quantity: int, actor_id: UUID, reason: str | None = None, ref_type: str | None = None, ref_id: UUID | None = None) -> StockMovement:
        stock = await session.get(StockItem, stock_id)
        if not stock:
            raise InventoryError("STOCK_NOT_FOUND", "Stock item not found")
        if stock.quantity_on_hand < quantity:
            raise InventoryError("INSUFFICIENT_STOCK", f"Available {stock.quantity_on_hand}, requested {quantity}")

        stock.quantity_on_hand -= quantity
        stock.updated_by = actor_id
        stock.version += 1

        movement = StockMovement(
            stock_item_id=stock_id,
            movement_type="DISPENSE",
            quantity=quantity,
            reference_type=ref_type,
            reference_id=ref_id,
            reason=reason,
            performed_by=actor_id,
            status="COMPLETED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(movement)
        await session.flush()

        await self._publish(session, "StockDispensed", {"stock_id": str(stock_id), "quantity": quantity, "location": stock.location})

        # Check reorder point
        item = await self.get_item(session, stock.item_id)
        if item and stock.quantity_on_hand <= item.reorder_point:
            alert = ReorderAlert(
                item_id=stock.item_id,
                location=stock.location,
                quantity_on_hand=stock.quantity_on_hand,
                reorder_point=item.reorder_point,
                status="OPEN",
                created_by=actor_id,
                updated_by=actor_id,
            )
            session.add(alert)
            await session.flush()
            await self._publish(session, "ReorderAlert", {"item_id": str(stock.item_id), "location": stock.location, "qty": stock.quantity_on_hand})

        return movement

    async def adjust_stock(self, session: AsyncSession, stock_id: UUID, new_quantity: int, actor_id: UUID, reason: str | None = None) -> StockMovement:
        stock = await session.get(StockItem, stock_id)
        if not stock:
            raise InventoryError("STOCK_NOT_FOUND", "Stock item not found")

        diff = new_quantity - stock.quantity_on_hand
        stock.quantity_on_hand = new_quantity
        stock.updated_by = actor_id
        stock.version += 1

        movement = StockMovement(
            stock_item_id=stock_id,
            movement_type="ADJUSTMENT",
            quantity=abs(diff),
            reason=reason,
            performed_by=actor_id,
            status="COMPLETED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(movement)
        await session.flush()
        await self._publish(session, "StockAdjusted", {"stock_id": str(stock_id), "old_qty": stock.quantity_on_hand - diff, "new_qty": new_quantity})
        return movement

    async def list_movements(self, session: AsyncSession, stock_item_id: UUID | None = None, movement_type: str | None = None, limit: int = 50, offset: int = 0) -> list[StockMovement]:
        stmt = select(StockMovement).where(StockMovement.deleted_at.is_(None))
        if stock_item_id:
            stmt = stmt.where(StockMovement.stock_item_id == stock_item_id)
        if movement_type:
            stmt = stmt.where(StockMovement.movement_type == movement_type)
        stmt = stmt.order_by(StockMovement.performed_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------ Reorder Alerts ------------------------

    async def list_reorder_alerts(self, session: AsyncSession, status: str | None = None, limit: int = 50, offset: int = 0) -> list[ReorderAlert]:
        stmt = select(ReorderAlert).where(ReorderAlert.deleted_at.is_(None))
        if status:
            stmt = stmt.where(ReorderAlert.status == status)
        stmt = stmt.order_by(ReorderAlert.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def resolve_alert(self, session: AsyncSession, alert_id: UUID, actor_id: UUID) -> ReorderAlert:
        alert = await session.get(ReorderAlert, alert_id)
        if not alert:
            raise InventoryError("ALERT_NOT_FOUND", "Alert not found")
        alert.status = "RESOLVED"
        alert.updated_by = actor_id
        alert.version += 1
        return alert

    # ------------------------ Expiring Stock Report ------------------------

    async def expiring_soon(self, session: AsyncSession, within_days: int = 30, location: str | None = None) -> list[StockItem]:
        from datetime import timedelta
        cutoff = datetime.utcnow() + timedelta(days=within_days)
        stmt = select(StockItem).where(
            StockItem.deleted_at.is_(None),
            StockItem.expiry_date.isnot(None),
            StockItem.expiry_date <= cutoff,
            StockItem.quantity_on_hand > 0,
        )
        if location:
            stmt = stmt.where(StockItem.location == location)
        stmt = stmt.order_by(StockItem.expiry_date)
        result = await session.execute(stmt)
        return list(result.scalars().all())


service = InventoryService()
