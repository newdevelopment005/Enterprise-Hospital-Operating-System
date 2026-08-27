// Pharmacy panel: medication catalog, stock, dispense to patient, history.

import { FormEvent, useState } from 'react'
import { pharmacyApi } from '../lib/client'
import type { DispensingRecord, PharmacyMedication, StockBatch } from '../lib/types'
import { PanelShell, fmt, useLoad } from './Panels'

export function PharmacyPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<PharmacyMedication | null>(null)
  const searchLoader = async () => pharmacyApi.searchMedications(query)
  const { data: meds, error: searchError, reload: reloadMeds } = useLoad(searchLoader)
  const stockLoader = async (): Promise<{ total: number; batches: StockBatch[] } | null> =>
    selected ? pharmacyApi.stock(selected.id) : null
  const { data: stock, reload: reloadStock } = useLoad(stockLoader)
  const { data: history, reload: reloadHistory } = useLoad(() => pharmacyApi.history(patientId))

  // dispense form
  const [quantity, setQuantity] = useState('1')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  // new medication form
  const [newCode, setNewCode] = useState('')
  const [newName, setNewName] = useState('')

  const dispense = async (e: FormEvent) => {
    e.preventDefault()
    if (!selected) return
    setBusy(true); setError(null); setMessage(null)
    try {
      const qty = Number(quantity)
      if (!qty || qty <= 0) throw new Error('Enter a quantity')
      await pharmacyApi.dispense({
        patient_id: patientId,
        medication_id: selected.id,
        quantity: qty,
        dispensed_by: authorId,
      })
      setMessage(`Dispensed ${qty} × ${selected.name}`)
      setQuantity('1')
      await Promise.all([reloadStock(), reloadHistory(), reloadMeds()])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Dispense failed')
    } finally {
      setBusy(false)
    }
  }

  const addMedication = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      if (!newCode.trim() || !newName.trim()) throw new Error('Code and name are required')
      await pharmacyApi.createMedication({ code: newCode.trim(), name: newName.trim() })
      setNewCode(''); setNewName('')
      await reloadMeds()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add medication')
    }
  }

  return (
    <PanelShell
      title="Pharmacy"
      error={searchError ?? error}
      addForm={
        <form onSubmit={addMedication} className="grid">
          <input placeholder="New med code (e.g. MED-010)" value={newCode} onChange={(e) => setNewCode(e.target.value)} />
          <input placeholder="New medication name" value={newName} onChange={(e) => setNewName(e.target.value)} />
          <button type="submit">Add to catalog</button>
        </form>
      }
    >
      <div className="grid">
        <input placeholder="Search medications…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <button onClick={() => void reloadMeds()}>Search</button>
      </div>

      <table>
        <thead>
          <tr><th>Code</th><th>Name</th><th>Form</th><th>Stock</th><th></th></tr>
        </thead>
        <tbody>
          {(meds?.medications ?? []).map((m: PharmacyMedication) => (
            <tr key={m.id}>
              <td className="mono">{m.code}</td>
              <td>{m.name}{m.controlled ? ' ⚠' : ''}</td>
              <td>{m.form ?? '—'}</td>
              <td className={m.total_stock <= 10 ? 'alert-error' : ''}>{m.total_stock}</td>
              <td>
                <button onClick={() => { setSelected(m); setMessage(null) }}>Select</button>
              </td>
            </tr>
          ))}
          {(meds?.medications?.length ?? 0) === 0 && (
            <tr><td colSpan={5} className="muted">No medications found.</td></tr>
          )}
        </tbody>
      </table>

      {selected && (
        <div className="card">
          <h4>{selected.name} — total in stock: {stock?.total ?? '…'}</h4>
          {(stock?.batches ?? []).length > 0 && (
            <p className="muted">
              Batches: {(stock!.batches as StockBatch[])
                .filter((b) => b.quantity > 0)
                .map((b) => `${b.batch_number ?? '?'} (${b.quantity}, exp ${b.expiry_date ?? '—'})`)
                .join(' · ')}
            </p>
          )}
          <form onSubmit={dispense} className="grid">
            <label>
              Quantity to dispense to this patient
              <input type="number" min={0.5} step="0.5" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            </label>
            <label>&nbsp;
              <button type="submit" disabled={busy}>{busy ? 'Dispensing…' : 'Dispense'}</button>
            </label>
          </form>
          {message && <p className="muted">{message}</p>}
        </div>
      )}

      <h4>Dispensing history — this patient</h4>
      <table>
        <thead>
          <tr><th>When</th><th>Qty</th><th>Batches</th><th>Status</th></tr>
        </thead>
        <tbody>
          {(history?.items ?? []).map((d: DispensingRecord) => (
            <tr key={d.id}>
              <td>{fmt(d.dispensed_at ?? undefined)}</td>
              <td>{d.quantity}</td>
              <td className="mono">{d.batch_number ?? '—'}</td>
              <td>{d.status}{d.returned_reason ? ` (${d.returned_reason})` : ''}</td>
            </tr>
          ))}
          {(history?.items?.length ?? 0) === 0 && (
            <tr><td colSpan={4} className="muted">Nothing dispensed to this patient yet.</td></tr>
          )}
        </tbody>
      </table>
    </PanelShell>
  )
}
