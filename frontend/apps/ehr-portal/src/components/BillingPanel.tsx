// Billing panel: add charges, issue invoice, record payments — hits billing-service.

import { FormEvent, useState } from 'react'
import { CHARGE_TYPES, billingApi } from '../lib/client'
import type { Charge, Invoice } from '../lib/types'
import { PanelShell, useLoad } from './Panels'

const PAY_METHODS = ['CASH', 'CARD', 'WALLET', 'BANK', 'INSURANCE', 'ONLINE']

export function BillingPanel({ patientId }: { patientId: string }) {
  const summaryLoader = async () => billingApi.summary(patientId)
  const { data: summary, error, reload } = useLoad(summaryLoader)

  // charge form
  const [itemType, setItemType] = useState('CONSULTATION')
  const [description, setDescription] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [unitPrice, setUnitPrice] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // payment dialog
  const [paying, setPaying] = useState<Invoice | null>(null)
  const [payAmount, setPayAmount] = useState('')
  const [payMethod, setPayMethod] = useState('CASH')
  const [message, setMessage] = useState<string | null>(null)

  const money = (v?: number, cur = '') =>
    v == null ? '—' : `${v.toFixed(2)}${cur ? ` ${cur}` : ''}`

  const addCharge = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setFormError(null)
    try {
      if (!description.trim() || !Number(unitPrice)) throw new Error('Description and unit price are required')
      await billingApi.addCharge({
        patient_id: patientId,
        item_type: itemType,
        description: description.trim(),
        quantity: Number(quantity) || 1,
        unit_price: Number(unitPrice),
      })
      setDescription(''); setUnitPrice(''); setQuantity('1')
      await reload()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to add charge')
    } finally {
      setBusy(false)
    }
  }

  const issueInvoice = () =>
    void (async () => {
      setFormError(null); setMessage(null)
      try {
        const inv = await billingApi.createInvoice(patientId)
        setMessage(`Invoice ${inv.invoice_number} issued for ${money(inv.total_amount, inv.currency)}`)
        await reload()
      } catch (err) {
        setFormError(err instanceof Error ? err.message : 'Failed to issue invoice')
      }
    })()

  const recordPayment = () =>
    void (async () => {
      if (!paying) return
      setFormError(null)
      try {
        const amount = Number(payAmount)
        if (!amount || amount <= 0) throw new Error('Enter a payment amount')
        const res = await billingApi.pay(paying.id, amount, payMethod)
        setPaying(null); setPayAmount('')
        setMessage(`Payment recorded — receipt ${res.receipt_number}`)
        await reload()
      } catch (err) {
        setFormError(err instanceof Error ? err.message : 'Payment failed')
      }
    })()

  return (
    <PanelShell
      title="Billing"
      error={error ?? formError}
      addForm={
        <form onSubmit={addCharge} className="stack">
          <div className="grid">
            <select value={itemType} onChange={(e) => setItemType(e.target.value)}>
              {CHARGE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input placeholder="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="grid">
            <label>
              Quantity
              <input type="number" min={0} step="0.5" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            </label>
            <label>
              Unit price
              <input type="number" min={0} step="0.01" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} />
            </label>
            <label>&nbsp;
              <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Add charge'}</button>
            </label>
          </div>
        </form>
      }
    >
      {summary && (
        <>
          <p className="muted">
            Billed {money(summary.totals.billed)} · Paid {money(summary.totals.paid)} ·{' '}
            Outstanding <strong>{money(summary.totals.outstanding)}</strong> ·{' '}
            {summary.pending_charge_count} pending charge(s)
          </p>

          <button onClick={issueInvoice} disabled={!summary.pending_charge_count}>
            Issue invoice from pending charges
          </button>
          {message && <p className="muted">{message}</p>}
        </>
      )}

      {paying && (
        <div className="card">
          <h4>Record payment — {paying.invoice_number} (balance {money(paying.balance_due ?? paying.patient_amount - paying.paid_amount)})</h4>
          <div className="grid">
            <input type="number" min={0} step="0.01" placeholder="Amount" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} />
            <select value={payMethod} onChange={(e) => setPayMethod(e.target.value)}>
              {PAY_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <button onClick={recordPayment}>Pay</button>
            <button onClick={() => { setPaying(null); setPayAmount('') }}>✕</button>
          </div>
        </div>
      )}

      <table>
        <thead>
          <tr><th>Invoice</th><th>Total</th><th>Paid</th><th>Status</th><th>Issued</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {(summary?.invoices ?? []).map((inv: Invoice) => (
            <tr key={inv.id}>
              <td className="mono">{inv.invoice_number}</td>
              <td>{money(inv.total_amount, inv.currency)}</td>
              <td>{money(inv.paid_amount)}</td>
              <td>{inv.status}</td>
              <td>{inv.issued_date}</td>
              <td>
                {!['PAID', 'VOID', 'CREDIT_NOTE'].includes(inv.status) && (
                  <button
                    onClick={() => {
                      setPaying(inv)
                      setPayAmount(String((inv.balance_due ?? inv.patient_amount - inv.paid_amount).toFixed(2)))
                    }}
                  >
                    Pay
                  </button>
                )}
              </td>
            </tr>
          ))}
          {(summary?.invoices?.length ?? 0) === 0 && (
            <tr><td colSpan={6} className="muted">No invoices yet. Add charges, then issue an invoice.</td></tr>
          )}
        </tbody>
      </table>

      <h4>Pending charges</h4>
      <ChargesTable patientId={patientId} />
    </PanelShell>
  )
}

function ChargesTable({ patientId }: { patientId: string }) {
  const { data } = useLoad(() => billingApi.listCharges(patientId))
  return (
    <table>
      <thead>
        <tr><th>Date</th><th>Type</th><th>Description</th><th>Qty</th><th>Unit</th><th>Status</th></tr>
      </thead>
      <tbody>
        {(data?.charges ?? []).slice(0, 20).map((c: Charge) => (
          <tr key={c.id}>
            <td>{c.service_date}</td>
            <td>{c.item_type}</td>
            <td className="clamp">{c.description}</td>
            <td>{c.quantity}</td>
            <td>{c.unit_price?.toFixed(2)}</td>
            <td>{c.status}</td>
          </tr>
        ))}
        {(data?.charges?.length ?? 0) === 0 && (
          <tr><td colSpan={6} className="muted">No charges recorded.</td></tr>
        )}
      </tbody>
    </table>
  )
}
