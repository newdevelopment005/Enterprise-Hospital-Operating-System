// Laboratory panel: test catalog, orders, samples, results.

import { FormEvent, useState } from 'react'
import { laboratoryApi } from '../lib/client'
import type { LabTest, LabOrder, LabOrderItemCreate, LabResult, LabResultCreate } from '../lib/types'
import { PanelShell, fmt, useLoad } from './Panels'

export function LaboratoryPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const [testQuery, setTestQuery] = useState('')
  const { data: tests, reload: reloadTests } = useLoad(() => laboratoryApi.listTests())
  const { data: orders, reload: reloadOrders } = useLoad(() => laboratoryApi.listOrders(patientId))
  const { data: results, reload: reloadResults } = useLoad(() => laboratoryApi.listResults(patientId))

  // Create order form
  const [orderItems, setOrderItems] = useState<LabOrderItemCreate[]>([{ test_id: '', test_name: '', specimen_type: '' }])
  const [orderBusy, setOrderBusy] = useState(false)
  const [orderError, setOrderError] = useState<string | null>(null)
  const [orderSuccess, setOrderSuccess] = useState<string | null>(null)

  // Create result form
  const [resultOrderId, setResultOrderId] = useState('')
  const [resultOrderItemId, setResultOrderItemId] = useState('')
  const [resultTestId, setResultTestId] = useState('')
  const [resultTestName, setResultTestName] = useState('')
  const [resultValue, setResultValue] = useState('')
  const [resultUnit, setResultUnit] = useState('')
  const [resultText, setResultText] = useState('')
  const [resultStatus, setResultStatus] = useState<'PRELIMINARY' | 'VERIFIED' | 'AMENDED' | 'CANCELLED'>('PRELIMINARY')
  const [resultBusy, setResultBusy] = useState(false)
  const [resultError, setResultError] = useState<string | null>(null)
  const [resultSuccess, setResultSuccess] = useState<string | null>(null)

  // Create test form
  const [newTestCode, setNewTestCode] = useState('')
  const [newTestName, setNewTestName] = useState('')
  const [newTestCategory, setNewTestCategory] = useState('CHEMISTRY')

  const handleCreateOrder = async (e: FormEvent) => {
    e.preventDefault()
    if (orderItems.length === 0) return
    setOrderBusy(true)
    setOrderError(null)
    setOrderSuccess(null)
    try {
      const items = orderItems
        .filter((i) => i.test_name.trim())
        .map((i) => ({
          test_id: i.test_id || undefined,
          test_name: i.test_name,
          specimen_type: i.specimen_type || undefined,
        }))
      if (items.length === 0) throw new Error('At least one test required')
      await laboratoryApi.createOrder({
        patient_id: patientId,
        ordering_doctor: authorId,
        priority: 'ROUTINE',
        items,
      })
      setOrderSuccess('Order created')
      setOrderItems([{ test_id: '', test_name: '', specimen_type: '' }])
      await Promise.all([reloadOrders(), reloadTests()])
    } catch (err) {
      setOrderError(err instanceof Error ? err.message : 'Failed to create order')
    } finally {
      setOrderBusy(false)
    }
  }

  const handleCreateResult = async (e: FormEvent) => {
    e.preventDefault()
    if (!resultOrderItemId || !resultTestId || !resultTestName) return
    setResultBusy(true)
    setResultError(null)
    setResultSuccess(null)
    try {
      const payload: LabResultCreate = {
        order_item_id: resultOrderItemId,
        patient_id: patientId,
        test_id: resultTestId,
        test_name: resultTestName,
        result_numeric: resultValue ? Number(resultValue) : undefined,
        result_text: resultText || undefined,
        unit: resultUnit || undefined,
        status: resultStatus,
      }
      await laboratoryApi.createResult(payload)
      setResultSuccess('Result recorded')
      setResultOrderItemId('')
      setResultTestId('')
      setResultTestName('')
      setResultValue('')
      setResultUnit('')
      setResultText('')
      await reloadResults()
    } catch (err) {
      setResultError(err instanceof Error ? err.message : 'Failed to create result')
    } finally {
      setResultBusy(false)
    }
  }

  const handleCreateTest = async (e: FormEvent) => {
    e.preventDefault()
    if (!newTestCode.trim() || !newTestName.trim()) return
    try {
      await laboratoryApi.createTest({
        code: newTestCode.trim(),
        name: newTestName.trim(),
        category: newTestCategory,
        is_active: true,
      })
      setNewTestCode('')
      setNewTestName('')
      await reloadTests()
    } catch (err) {
      setOrderError(err instanceof Error ? err.message : 'Failed to create test')
    }
  }

  const addOrderItem = () => setOrderItems([...orderItems, { test_id: '', test_name: '', specimen_type: '' }])
  const removeOrderItem = (idx: number) => setOrderItems(orderItems.filter((_, i) => i !== idx))

  const orderItemsForOrder = (order: LabOrder) => order.items

  return (
    <PanelShell
      title="Laboratory"
      addForm={
        <form onSubmit={handleCreateTest} className="grid">
          <input placeholder="Test code (e.g. CBC)" value={newTestCode} onChange={(e) => setNewTestCode(e.target.value)} />
          <input placeholder="Test name (e.g. Complete Blood Count)" value={newTestName} onChange={(e) => setNewTestName(e.target.value)} />
          <select value={newTestCategory} onChange={(e) => setNewTestCategory(e.target.value)}>
            <option value="HEMATOLOGY">Hematology</option>
            <option value="CHEMISTRY">Chemistry</option>
            <option value="MICROBIOLOGY">Microbiology</option>
            <option value="IMMUNOLOGY">Immunology</option>
            <option value="COAGULATION">Coagulation</option>
          </select>
          <button type="submit">Add to catalog</button>
        </form>
      }
    >
      {/* Test Catalog */}
      <h3>Test Catalog</h3>
      <div className="grid">
        <input placeholder="Search tests…" value={testQuery} onChange={(e) => setTestQuery(e.target.value)} />
      </div>
      <table>
        <thead>
          <tr><th>Code</th><th>Name</th><th>Category</th><th>Reference</th><th>Active</th></tr>
        </thead>
        <tbody>
          {(tests?.items ?? []).filter((t: LabTest) => !testQuery || t.code.toLowerCase().includes(testQuery.toLowerCase()) || t.name.toLowerCase().includes(testQuery.toLowerCase())).map((t: LabTest) => (
            <tr key={t.id}>
              <td className="mono">{t.code}</td>
              <td>{t.name}</td>
              <td>{t.category}</td>
              <td>{t.reference_low !== null && t.reference_high !== null ? `${t.reference_low}–${t.reference_high} ${t.unit ?? ''}` : '—'}</td>
              <td>{t.is_active ? '✓' : '✗'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Orders for this patient */}
      <h3>Lab Orders — this patient</h3>
      <form onSubmit={handleCreateOrder} className="card">
        <h4>Create new order</h4>
        {orderItems.map((item, idx) => (
          <div key={idx} className="grid">
            <select value={item.test_id} onChange={(e) => setOrderItems(orderItems.map((i, i2) => i2 === idx ? { ...i, test_id: e.target.value } : i))}>
              <option value="">— Select test —</option>
              {(tests?.items ?? []).filter((t: LabTest) => t.is_active).map((t: LabTest) => (
                <option key={t.id} value={t.id}>{t.code} — {t.name}</option>
              ))}
            </select>
            <input placeholder="Custom test name" value={item.test_name} onChange={(e) => setOrderItems(orderItems.map((i, i2) => i2 === idx ? { ...i, test_name: e.target.value } : i))} />
            <input placeholder="Specimen type (e.g. BLOOD)" value={item.specimen_type} onChange={(e) => setOrderItems(orderItems.map((i, i2) => i2 === idx ? { ...i, specimen_type: e.target.value } : i))} />
            <button type="button" onClick={() => removeOrderItem(idx)} disabled={orderItems.length === 1}>Remove</button>
          </div>
        ))}
        <button type="button" onClick={addOrderItem}>+ Add test</button>
        <button type="submit" disabled={orderBusy}>{orderBusy ? 'Creating…' : 'Create Order'}</button>
        {orderError && <p className="alert-error">{orderError}</p>}
        {orderSuccess && <p className="muted">{orderSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>ID</th><th>Priority</th><th>Status</th><th>Tests</th><th>Ordered</th></tr>
        </thead>
        <tbody>
          {(orders?.items ?? []).map((o: LabOrder) => (
            <tr key={o.id}>
              <td className="mono">{o.id.slice(0, 8)}…</td>
              <td>{o.priority}</td>
              <td>{o.status}</td>
              <td>{orderItemsForOrder(o).map((i) => i.test_name).join(', ') || '—'}</td>
              <td>{fmt(o.ordered_at)}</td>
            </tr>
          ))}
          {(orders?.items?.length ?? 0) === 0 && <tr><td colSpan={5} className="muted">No orders for this patient.</td></tr>}
        </tbody>
      </table>

      {/* Results for this patient */}
      <h3>Lab Results — this patient</h3>
      <form onSubmit={handleCreateResult} className="card">
        <h4>Record result</h4>
        <div className="grid">
          <select value={resultOrderId} onChange={(e) => setResultOrderId(e.target.value)}>
            <option value="">— Select order —</option>
            {(orders?.items ?? []).map((o: LabOrder) => (
              <option key={o.id} value={o.id}>{o.id.slice(0, 8)}… ({o.status})</option>
            ))}
          </select>
          <select value={resultOrderItemId} onChange={(e) => { setResultOrderItemId(e.target.value); const item = orders?.items?.flatMap(o => o.items).find(i => i.id === e.target.value); if (item) { setResultTestId(item.test_id || ''); setResultTestName(item.test_name); } }}>
            <option value="">— Select test —</option>
            {(orders?.items ?? []).flatMap((o: LabOrder) => o.items.map((i) => ({ ...i, orderId: o.id }))).map((i) => (
              <option key={i.id} value={i.id}>{i.test_name} (order {i.orderId.slice(0, 8)}…)</option>
            ))}
          </select>
          <input placeholder="Test ID" value={resultTestId} onChange={(e) => setResultTestId(e.target.value)} />
          <input placeholder="Test name" value={resultTestName} onChange={(e) => setResultTestName(e.target.value)} />
        </div>
        <div className="grid">
          <input type="number" step="0.01" placeholder="Numeric value" value={resultValue} onChange={(e) => setResultValue(e.target.value)} />
          <input placeholder="Unit" value={resultUnit} onChange={(e) => setResultUnit(e.target.value)} />
          <input placeholder="Text value" value={resultText} onChange={(e) => setResultText(e.target.value)} />
          <select value={resultStatus} onChange={(e) => setResultStatus(e.target.value as 'PRELIMINARY' | 'VERIFIED' | 'AMENDED' | 'CANCELLED')}>
            <option value="PRELIMINARY">Preliminary</option>
            <option value="VERIFIED">Verified</option>
            <option value="AMENDED">Amended</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </div>
        <button type="submit" disabled={resultBusy}>{resultBusy ? 'Recording…' : 'Record Result'}</button>
        {resultError && <p className="alert-error">{resultError}</p>}
        {resultSuccess && <p className="muted">{resultSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>Test</th><th>Value</th><th>Unit</th><th>Flag</th><th>Status</th><th>Performed</th></tr>
        </thead>
        <tbody>
          {(results?.items ?? []).map((r: LabResult) => (
            <tr key={r.id}>
              <td>{r.test_name}</td>
              <td className="mono">{r.result_numeric !== undefined ? r.result_numeric : r.result_text ?? '—'}</td>
              <td>{r.unit ?? '—'}</td>
              <td>{r.flag ?? '—'}</td>
              <td>{r.status}</td>
              <td>{fmt(r.performed_at ?? undefined)}</td>
            </tr>
          ))}
          {(results?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No results for this patient.</td></tr>}
        </tbody>
      </table>
    </PanelShell>
  )
}