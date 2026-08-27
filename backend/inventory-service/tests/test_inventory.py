"""Inventory service tests."""

import uuid

import pytest

from inventory_service.dto.schemas import ItemCreate, ItemUpdate, StockItemCreate
from inventory_service.service.inventory_service import InventoryError


async def _create_item(session, svc, actor_id, sku="MED-001", name="Amoxicillin 500mg", category="MEDICATION", uom="tablet", reorder_point=100, reorder_qty=500):
    payload = ItemCreate(sku=sku, name=name, category=category, unit_of_measure=uom, unit_cost=0.50, reorder_point=reorder_point, reorder_qty=reorder_qty)
    return await svc.create_item(session, payload, actor_id)


async def _create_stock(session, svc, actor_id, item_id, location="PHARMACY-A", lot="LOT-001", qty=200):
    payload = StockItemCreate(item_id=item_id, location=location, lot_number=lot, quantity_on_hand=qty)
    return await svc.create_stock_item(session, payload, actor_id)


class TestItemCatalog:
    async def test_create_item(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id)
        assert item.id
        assert item.sku == "MED-001"
        assert item.status == "ACTIVE"

    async def test_duplicate_sku_rejected(self, session, svc, actor_id):
        await _create_item(session, svc, actor_id, "MED-001")
        with pytest.raises(InventoryError, match="already exists"):
            await _create_item(session, svc, actor_id, "MED-001", "Another")

    async def test_list_items(self, session, svc, actor_id):
        await _create_item(session, svc, actor_id, "A", "Item A")
        await _create_item(session, svc, actor_id, "B", "Item B")
        items = await svc.list_items(session)
        assert len(items) == 2

    async def test_update_item(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id)
        updated = await svc.update_item(session, item.id, ItemUpdate(name="Amoxicillin 250mg"), actor_id)
        assert updated.name == "Amoxicillin 250mg"
        assert updated.version == 2

    async def test_deactivate_item(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id)
        await svc.deactivate_item(session, item.id, actor_id)
        items = await svc.list_items(session)
        assert len(items) == 0


class TestStockItems:
    async def test_create_stock(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id)
        stock = await _create_stock(session, svc, actor_id, item.id)
        assert stock.id
        assert stock.quantity_on_hand == 200

    async def test_duplicate_stock_rejected(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id)
        await _create_stock(session, svc, actor_id, item.id)
        with pytest.raises(InventoryError, match="already exists"):
            await _create_stock(session, svc, actor_id, item.id)

    async def test_list_stock_by_item(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id)
        await _create_stock(session, svc, actor_id, item.id, "LOC-A", "LOT-1")
        await _create_stock(session, svc, actor_id, item.id, "LOC-B", "LOT-2")
        items = await svc.list_stock_items(session, item_id=item.id)
        assert len(items) == 2


class TestStockMovements:
    async def test_receive_stock(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id)
        stock = await _create_stock(session, svc, actor_id, item.id, qty=100)
        movement = await svc.receive_stock(session, stock.id, 50, actor_id, reason="PO-001")
        assert movement.movement_type == "RECEIPT"
        assert movement.quantity == 50
        refreshed = await svc.get_stock_item(session, stock.id)
        assert refreshed.quantity_on_hand == 150

    async def test_dispense_stock(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id)
        stock = await _create_stock(session, svc, actor_id, item.id, qty=100)
        movement = await svc.dispense_stock(session, stock.id, 30, actor_id, reason="prescription")
        assert movement.movement_type == "DISPENSE"
        refreshed = await svc.get_stock_item(session, stock.id)
        assert refreshed.quantity_on_hand == 70

    async def test_dispense_insufficient_rejected(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id)
        stock = await _create_stock(session, svc, actor_id, item.id, qty=10)
        with pytest.raises(InventoryError, match="Available"):
            await svc.dispense_stock(session, stock.id, 20, actor_id)

    async def test_adjust_stock(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id)
        stock = await _create_stock(session, svc, actor_id, item.id, qty=100)
        await svc.adjust_stock(session, stock.id, 95, actor_id, reason="physical count")
        refreshed = await svc.get_stock_item(session, stock.id)
        assert refreshed.quantity_on_hand == 95

    async def test_reorder_alert_generated(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id, reorder_point=10)
        stock = await _create_stock(session, svc, actor_id, item.id, qty=15)
        await svc.dispense_stock(session, stock.id, 8, actor_id)
        alerts = await svc.list_reorder_alerts(session)
        assert len(alerts) == 1
        assert alerts[0].quantity_on_hand == 7


class TestReorderAlerts:
    async def test_resolve_alert(self, session, svc, actor_id):
        item = await _create_item(session, svc, actor_id, reorder_point=10)
        stock = await _create_stock(session, svc, actor_id, item.id, qty=15)
        await svc.dispense_stock(session, stock.id, 8, actor_id)
        alerts = await svc.list_reorder_alerts(session)
        resolved = await svc.resolve_alert(session, alerts[0].id, actor_id)
        assert resolved.status == "RESOLVED"

    async def test_resolve_nonexistent_alert(self, session, svc, actor_id):
        with pytest.raises(InventoryError, match="not found"):
            await svc.resolve_alert(session, uuid.uuid4(), actor_id)


class TestExpiringStock:
    async def test_expiring_soon(self, session, svc, actor_id):
        from datetime import timedelta
        item = await _create_item(session, svc, actor_id)
        payload = StockItemCreate(
            item_id=item.id, location="PHARM", lot_number="EXP-001",
            expiry_date=datetime.utcnow() + timedelta(days=10), quantity_on_hand=50,
        )
        stock = await svc.create_stock_item(session, payload, actor_id)
        results = await svc.expiring_soon(session, within_days=30)
        assert len(results) == 1
        assert results[0].id == stock.id

    async def test_not_expiring_item_excluded(self, session, svc, actor_id):
        from datetime import timedelta
        item = await _create_item(session, svc, actor_id)
        payload = StockItemCreate(
            item_id=item.id, location="PHARM", lot_number="FAR-001",
            expiry_date=datetime.utcnow() + timedelta(days=365), quantity_on_hand=50,
        )
        await svc.create_stock_item(session, payload, actor_id)
        results = await svc.expiring_soon(session, within_days=30)
        assert len(results) == 0


# Need datetime import for expiring tests
from datetime import datetime
