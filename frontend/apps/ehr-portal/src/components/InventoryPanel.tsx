// Inventory panel: item catalog, stock on hand, stock movements, reorder alerts.

import { FormEvent, useState } from 'react'
import { inventoryApi } from '../lib/client'
import type { InventoryItem, InventoryItemCreate, StockItem, StockItemCreate, StockMovementCreate } from '../lib/types'
import { PanelShell, fmt, useLoad } from './Panels'

export function InventoryPanel({ authorId }: { patientId: string; authorId: string }) {
  const { data: items, reload: reloadItems } = useLoad(() => inventoryApi.listItems())
  const { data: stock, reload: reloadStock } = useLoad(() => inventoryApi.listStock())
  const { data: expiring, reload: reloadExpiring } = useLoad(() => inventoryApi.expiring(30))
  const { data: alerts, reload: reloadAlerts } = useLoad(() => inventoryApi.listAlerts())

  // Create item form
  const [sku, setSku] = useState('')
  const [name, setName] = useState('')
  const [category, setCategory] = useState('GENERAL')
  const [uom, setUom] = useState('EACH')
  const [reorderPoint, setReorderPoint] = useState('10')
  const [itemBusy, setItemBusy] = useState(false)
  const [itemError, setItemError] = useState<string | null>(null)
  const [itemSuccess, setItemSuccess] = useState<string | null>(null)

  // Create stock form
  const [stockItemId, setStockItemId] = useState('')
  const [location, setLocation] = useState('MAIN')
  const [lotNumber, setLotNumber] = useState('')
  const [expiryDate, setExpiryDate] = useState('')
  const [qtyOnHand, setQtyOnHand] = useState('0')
  const [stockBusy, setStockBusy] = useState(false)
  const [stockError, setStockError] = useState<string | null>(null)
  const [stockSuccess, setStockSuccess] = useState<string | null>(null)

  // Movement form
  const [movementStockId, setMovementStockId] = useState('')
  const [moveType, setMoveType] = useState<'RECEIPT' | 'DISPENSE'>('RECEIPT')
  const [moveQty, setMoveQty] = useState('1')
  const [moveReason, setMoveReason] = useState('')
  const [moveBusy, setMoveBusy] = useState(false)
  const [moveError, setMoveError] = useState<string | null>(null)
  const [moveSuccess, setMoveSuccess] = useState<string | null>(null)
  const { data: movements, reload: reloadMovements } = useLoad(() => inventoryApi.listMovements())

  const handleCreateItem = async (e: FormEvent) => {
    e.preventDefault()
    if (!sku.trim() || !name.trim()) return
    setItemBusy(true)
    setItemError(null)
    setItemSuccess(null)
    try {
      const payload: InventoryItemCreate = {
        sku: sku.trim(),
        name: name.trim(),
        category,
        unit_of_measure: uom,
        reorder_point: Number(reorderPoint) || 0,
      }
      await inventoryApi.createItem(payload)
      setItemSuccess('Item added to catalog')
      setSku('')
      setName('')
      await reloadItems()
    } catch (err) {
      setItemError(err instanceof Error ? err.message : 'Failed to create item')
    } finally {
      setItemBusy(false)
    }
  }

  const handleCreateStock = async (e: FormEvent) => {
    e.preventDefault()
    if (!stockItemId) return
    setStockBusy(true)
    setStockError(null)
    setStockSuccess(null)
    try {
      const payload: StockItemCreate = {
        item_id: stockItemId,
        location,
        lot_number: lotNumber.trim() || undefined,
        expiry_date: expiryDate || undefined,
        quantity_on_hand: Number(qtyOnHand) || 0,
      }
      await inventoryApi.createStock(payload)
      setStockSuccess('Stock created')
      setLotNumber('')
      setExpiryDate('')
      setQtyOnHand('0')
      await Promise.all([reloadStock(), reloadExpiring()])
    } catch (err) {
      setStockError(err instanceof Error ? err.message : 'Failed to create stock')
    } finally {
      setStockBusy(false)
    }
  }

  const handleMove = async (e: FormEvent) => {
    e.preventDefault()
    if (!movementStockId || !moveQty) return
    setMoveBusy(true)
    setMoveError(null)
    setMoveSuccess(null)
    try {
      const payload: StockMovementCreate = {
        stock_item_id: movementStockId,
        movement_type: moveType,
        quantity: Number(moveQty),
        reason: moveReason.trim() || undefined,
        performed_by: authorId,
      }
      if (moveType === 'RECEIPT') await inventoryApi.receive(movementStockId, payload)
      else await inventoryApi.dispense(movementStockId, payload)
      setMoveSuccess(moveType === 'RECEIPT' ? 'Stock received' : 'Stock dispensed')
      setMoveQty('1')
      setMoveReason('')
      await Promise.all([reloadStock(), reloadAlerts(), reloadMovements(), reloadExpiring()])
    } catch (err) {
      setMoveError(err instanceof Error ? err.message : 'Failed to record movement')
    } finally {
      setMoveBusy(false)
    }
  }

  const handleResolveAlert = async (alertId: string) => {
    try {
      await inventoryApi.resolveAlert(alertId)
      await reloadAlerts()
    } catch (err) {
      setMoveError(err instanceof Error ? err.message : 'Failed to resolve alert')
    }
  }

  const itemName = (id: string) => items?.items?.find((i: InventoryItem) => i.id === id)?.name ?? '?'

  return (
    <PanelShell
      title="Inventory"
      addForm={
        <form onSubmit={handleCreateItem} className="grid">
          <input placeholder="SKU" value={sku} onChange={(e) => setSku(e.target.value)} />
          <input placeholder="Item name" value={name} onChange={(e) => setName(e.target.value)} />
          <input placeholder="Category" value={category} onChange={(e) => setCategory(e.target.value)} />
          <input placeholder="Unit of measure" value={uom} onChange={(e) => setUom(e.target.value)} />
          <input type="number" placeholder="Reorder point" value={reorderPoint} onChange={(e) => setReorderPoint(e.target.value)} />
          <button type="submit" disabled={itemBusy}>{itemBusy ? 'Adding…' : 'Add to catalog'}</button>
          {itemError && <p className="alert-error">{itemError}</p>}
          {itemSuccess && <p className="muted">{itemSuccess}</p>}
        </form>
      }
    >
      {/* Item catalog */}
      <h3>Item Catalog</h3>
      <table>
        <thead>
          <tr><th>SKU</th><th>Name</th><th>Category</th><th>UOM</th><th>Reorder</th><th>Active</th></tr>
        </thead>
        <tbody>
          {(items?.items ?? []).map((i: InventoryItem) => (
            <tr key={i.id}>
              <td className="mono">{i.sku}</td>
              <td>{i.name}</td>
              <td>{i.category}</td>
              <td>{i.unit_of_measure}</td>
              <td>{i.reorder_point}</td>
              <td>{i.is_active ? '✓' : '✗'}</td>
            </tr>
          ))}
          {(items?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No items in catalog.</td></tr>}
        </tbody>
      </table>

      {/* Stock on hand */}
      <h3>Stock on Hand</h3>
      <form onSubmit={handleCreateStock} className="card">
        <h4>Add stock</h4>
        <div className="grid">
          <select value={stockItemId} onChange={(e) => setStockItemId(e.target.value)}>
            <option value="">— Select item —</option>
            {(items?.items ?? []).filter((i: InventoryItem) => i.is_active).map((i: InventoryItem) => (
              <option key={i.id} value={i.id}>{i.sku} — {i.name}</option>
            ))}
          </select>
          <input placeholder="Location (e.g. MAIN)" value={location} onChange={(e) => setLocation(e.target.value)} />
          <input placeholder="Lot number" value={lotNumber} onChange={(e) => setLotNumber(e.target.value)} />
          <input type="date" placeholder="Expiry" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} />
          <input type="number" placeholder="Qty on hand" value={qtyOnHand} onChange={(e) => setQtyOnHand(e.target.value)} />
        </div>
        <button type="submit" disabled={stockBusy}>{stockBusy ? 'Adding…' : 'Create Stock'}</button>
        {stockError && <p className="alert-error">{stockError}</p>}
        {stockSuccess && <p className="muted">{stockSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>Item</th><th>Location</th><th>Lot</th><th>Expiry</th><th>On hand</th><th>Reserved</th></tr>
        </thead>
        <tbody>
          {(stock?.items ?? []).map((s: StockItem) => (
            <tr key={s.id}>
              <td>{itemName(s.item_id)}</td>
              <td>{s.location}</td>
              <td>{s.lot_number ?? '—'}</td>
              <td>{fmt(s.expiry_date ?? undefined)}</td>
              <td className="mono">{s.quantity_on_hand}</td>
              <td className="mono">{s.quantity_reserved}</td>
            </tr>
          ))}
          {(stock?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No stock recorded.</td></tr>}
        </tbody>
      </table>

      {/* Movements */}
      <h3>Stock Movements</h3>
      <form onSubmit={handleMove} className="card">
        <h4>Record receive / dispense</h4>
        <div className="grid">
          <select value={movementStockId} onChange={(e) => setMovementStockId(e.target.value)}>
            <option value="">— Select stock —</option>
            {(stock?.items ?? []).map((s: StockItem) => (
              <option key={s.id} value={s.id}>{itemName(s.item_id)} @ {s.location} ({s.quantity_on_hand} on hand)</option>
            ))}
          </select>
          <select value={moveType} onChange={(e) => setMoveType(e.target.value as 'RECEIPT' | 'DISPENSE')}>
            <option value="RECEIPT">Receipt</option>
            <option value="DISPENSE">Dispense</option>
          </select>
          <input type="number" min="1" placeholder="Quantity" value={moveQty} onChange={(e) => setMoveQty(e.target.value)} />
          <input placeholder="Reason" value={moveReason} onChange={(e) => setMoveReason(e.target.value)} />
        </div>
        <button type="submit" disabled={moveBusy}>{moveBusy ? 'Recording…' : 'Record Movement'}</button>
        {moveError && <p className="alert-error">{moveError}</p>}
        {moveSuccess && <p className="muted">{moveSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>Type</th><th>Stock</th><th>Qty</th><th>Reason</th><th>Performed</th></tr>
        </thead>
        <tbody>
          {(movements?.items ?? []).map((m) => (
            <tr key={m.id}>
              <td>{m.movement_type}</td>
              <td>{itemName((stock?.items ?? []).find((s: StockItem) => s.id === m.stock_item_id)?.item_id ?? '')}</td>
              <td className="mono">{m.quantity}</td>
              <td>{m.reason ?? '—'}</td>
              <td>{fmt(m.performed_at)}</td>
            </tr>
          ))}
          {(movements?.items?.length ?? 0) === 0 && <tr><td colSpan={5} className="muted">No movements recorded.</td></tr>}
        </tbody>
      </table>

      {/* Alerts */}
      <h3>Reorder Alerts</h3>
      <table>
        <thead>
          <tr><th>Item</th><th>Location</th><th>On hand</th><th>Reorder point</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          {(alerts?.items ?? []).map((a) => (
            <tr key={a.id}>
              <td>{itemName(a.item_id)}</td>
              <td>{a.location}</td>
              <td className="mono">{a.quantity_on_hand}</td>
              <td className="mono">{a.reorder_point}</td>
              <td>{a.status}</td>
              <td><button onClick={() => handleResolveAlert(a.id)} disabled={a.status !== 'OPEN'}>Resolve</button></td>
            </tr>
          ))}
          {(alerts?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No alerts.</td></tr>}
        </tbody>
      </table>

      {/* Expiring stock */}
      <h3>Expiring Soon (30d)</h3>
      <table>
        <thead>
          <tr><th>Item</th><th>Location</th><th>Lot</th><th>Expiry</th><th>On hand</th></tr>
        </thead>
        <tbody>
          {(expiring ?? []).map((s: StockItem) => (
            <tr key={s.id}>
              <td>{itemName(s.item_id)}</td>
              <td>{s.location}</td>
              <td>{s.lot_number ?? '—'}</td>
              <td>{fmt(s.expiry_date ?? undefined)}</td>
              <td className="mono">{s.quantity_on_hand}</td>
            </tr>
          ))}
          {(expiring?.length ?? 0) === 0 && <tr><td colSpan={5} className="muted">Nothing expiring soon.</td></tr>}
        </tbody>
      </table>
    </PanelShell>
  )
}