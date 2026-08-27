// Radiology panel: modality catalog, orders, studies, reports.

import { FormEvent, useState } from 'react'
import { radiologyApi } from '../lib/client'
import { PanelShell, fmt, useLoad } from './Panels'

export function RadiologyPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const [modQuery, setModQuery] = useState('')
  const { data: modalities, reload: reloadModalities } = useLoad(() => radiologyApi.listModalities())
  const { data: orders, reload: reloadOrders } = useLoad(() => radiologyApi.listOrders(patientId))
  const { data: reports, reload: reloadReports } = useLoad(() => radiologyApi.listReports(patientId))

  // Order form
  const [orderModality, setOrderModality] = useState('')
  const [orderRegion, setOrderRegion] = useState('')
  const [orderIndication, setOrderIndication] = useState('')
  const [orderPriority, setOrderPriority] = useState<'ROUTINE' | 'URGENT' | 'STAT'>('ROUTINE')
  const [orderContrast, setOrderContrast] = useState(false)
  const [orderBusy, setOrderBusy] = useState(false)
  const [orderError, setOrderError] = useState<string | null>(null)
  const [orderSuccess, setOrderSuccess] = useState<string | null>(null)

  // Study form
  const [studyOrderId, setStudyOrderId] = useState('')
  const [studyRegion, setStudyRegion] = useState('')
  const [studyModality, setStudyModality] = useState('')
  const [studyBusy, setStudyBusy] = useState(false)
  const [studyError, setStudyError] = useState<string | null>(null)

  // Report form
  const [reportOrderId, setReportOrderId] = useState('')
  const [reportFindings, setReportFindings] = useState('')
  const [reportImpression, setReportImpression] = useState('')
  const [reportRecommendation, setReportRecommendation] = useState('')
  const [reportBusy, setReportBusy] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)
  const [reportSuccess, setReportSuccess] = useState<string | null>(null)

  // Modality form
  const [newModCode, setNewModCode] = useState('')
  const [newModName, setNewModName] = useState('')

  const handleCreateOrder = async (e: FormEvent) => {
    e.preventDefault()
    if (!orderModality || !orderRegion) return
    setOrderBusy(true)
    setOrderError(null)
    setOrderSuccess(null)
    try {
      await radiologyApi.createOrder({
        patient_id: patientId,
        ordering_doctor: authorId,
        modality_code: orderModality,
        body_region: orderRegion,
        clinical_indication: orderIndication || undefined,
        priority: orderPriority,
        contrast: orderContrast,
      })
      setOrderSuccess('Order created')
      setOrderModality('')
      setOrderRegion('')
      setOrderIndication('')
      await reloadOrders()
    } catch (err) {
      setOrderError(err instanceof Error ? err.message : 'Failed')
    } finally {
      setOrderBusy(false)
    }
  }

  const handleCreateStudy = async (e: FormEvent) => {
    e.preventDefault()
    if (!studyOrderId) return
    setStudyBusy(true)
    setStudyError(null)
    try {
      const order = orders?.items.find((o) => o.id === studyOrderId)
      await radiologyApi.createStudy({
        order_id: studyOrderId,
        patient_id: patientId,
        modality_code: studyModality || order?.modality_code || '',
        body_region: studyRegion || order?.body_region || '',
      })
      setStudyOrderId('')
      await reloadOrders()
    } catch (err) {
      setStudyError(err instanceof Error ? err.message : 'Failed')
    } finally {
      setStudyBusy(false)
    }
  }

  const handleCreateReport = async (e: FormEvent) => {
    e.preventDefault()
    if (!reportOrderId) return
    setReportBusy(true)
    setReportError(null)
    setReportSuccess(null)
    try {
      await radiologyApi.createReport({
        order_id: reportOrderId,
        patient_id: patientId,
        findings: reportFindings || undefined,
        impression: reportImpression || undefined,
        recommendation: reportRecommendation || undefined,
      })
      setReportSuccess('Report created')
      setReportOrderId('')
      setReportFindings('')
      setReportImpression('')
      setReportRecommendation('')
      await reloadReports()
    } catch (err) {
      setReportError(err instanceof Error ? err.message : 'Failed')
    } finally {
      setReportBusy(false)
    }
  }

  const handleCreateModality = async (e: FormEvent) => {
    e.preventDefault()
    if (!newModCode.trim() || !newModName.trim()) return
    try {
      await radiologyApi.createModality({ code: newModCode.trim(), name: newModName.trim() })
      setNewModCode('')
      setNewModName('')
      await reloadModalities()
    } catch (err) {
      setOrderError(err instanceof Error ? err.message : 'Failed')
    }
  }

  return (
    <PanelShell
      title="Radiology"
      addForm={
        <form onSubmit={handleCreateModality} className="grid">
          <input placeholder="Code (e.g. CT)" value={newModCode} onChange={(e) => setNewModCode(e.target.value)} />
          <input placeholder="Name (e.g. Computed Tomography)" value={newModName} onChange={(e) => setNewModName(e.target.value)} />
          <button type="submit">Add modality</button>
        </form>
      }
    >
      {/* Modality catalog */}
      <h3>Imaging Modalities</h3>
      <div className="grid">
        <input placeholder="Search modalities…" value={modQuery} onChange={(e) => setModQuery(e.target.value)} />
      </div>
      <table>
        <thead>
          <tr><th>Code</th><th>Name</th><th>Description</th><th>Active</th></tr>
        </thead>
        <tbody>
          {(modalities?.items ?? []).filter((m) => !modQuery || m.code.toLowerCase().includes(modQuery.toLowerCase()) || m.name.toLowerCase().includes(modQuery.toLowerCase())).map((m) => (
            <tr key={m.id}>
              <td className="mono">{m.code}</td>
              <td>{m.name}</td>
              <td>{m.description ?? '—'}</td>
              <td>{m.is_active ? '✓' : '✗'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Orders */}
      <h3>Radiology Orders — this patient</h3>
      <form onSubmit={handleCreateOrder} className="card">
        <h4>New order</h4>
        <div className="grid">
          <select value={orderModality} onChange={(e) => setOrderModality(e.target.value)}>
            <option value="">— Modality —</option>
            {(modalities?.items ?? []).filter((m) => m.is_active).map((m) => (
              <option key={m.id} value={m.code}>{m.code} — {m.name}</option>
            ))}
          </select>
          <input placeholder="Body region" value={orderRegion} onChange={(e) => setOrderRegion(e.target.value)} />
          <input placeholder="Clinical indication" value={orderIndication} onChange={(e) => setOrderIndication(e.target.value)} />
          <select value={orderPriority} onChange={(e) => setOrderPriority(e.target.value as 'ROUTINE' | 'URGENT' | 'STAT')}>
            <option value="ROUTINE">Routine</option>
            <option value="URGENT">Urgent</option>
            <option value="STAT">STAT</option>
          </select>
          <label><input type="checkbox" checked={orderContrast} onChange={(e) => setOrderContrast(e.target.checked)} /> Contrast</label>
        </div>
        <button type="submit" disabled={orderBusy}>{orderBusy ? 'Creating…' : 'Create Order'}</button>
        {orderError && <p className="alert-error">{orderError}</p>}
        {orderSuccess && <p className="muted">{orderSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>ID</th><th>Modality</th><th>Region</th><th>Priority</th><th>Status</th><th>Ordered</th></tr>
        </thead>
        <tbody>
          {(orders?.items ?? []).map((o) => (
            <tr key={o.id}>
              <td className="mono">{o.id.slice(0, 8)}…</td>
              <td>{o.modality_code}</td>
              <td>{o.body_region}</td>
              <td>{o.priority}</td>
              <td>{o.status}</td>
              <td>{fmt(o.ordered_at)}</td>
            </tr>
          ))}
          {(orders?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No orders.</td></tr>}
        </tbody>
      </table>

      {/* Study creation */}
      <h3>Record Study</h3>
      <form onSubmit={handleCreateStudy} className="card">
        <div className="grid">
          <select value={studyOrderId} onChange={(e) => setStudyOrderId(e.target.value)}>
            <option value="">— Select order —</option>
            {(orders?.items ?? []).filter((o) => o.status !== 'CANCELLED').map((o) => (
              <option key={o.id} value={o.id}>{o.modality_code} {o.body_region} ({o.status})</option>
            ))}
          </select>
          <input placeholder="Study modality (overrides order)" value={studyModality} onChange={(e) => setStudyModality(e.target.value)} />
          <input placeholder="Body region (overrides order)" value={studyRegion} onChange={(e) => setStudyRegion(e.target.value)} />
        </div>
        <button type="submit" disabled={studyBusy}>{studyBusy ? 'Creating…' : 'Create Study'}</button>
        {studyError && <p className="alert-error">{studyError}</p>}
      </form>

      {/* Reports */}
      <h3>Radiology Reports</h3>
      <form onSubmit={handleCreateReport} className="card">
        <h4>Draft report</h4>
        <div className="grid">
          <select value={reportOrderId} onChange={(e) => setReportOrderId(e.target.value)}>
            <option value="">— Select order —</option>
            {(orders?.items ?? []).filter((o) => o.status === 'COMPLETED').map((o) => (
              <option key={o.id} value={o.id}>{o.modality_code} {o.body_region} ({fmt(o.ordered_at)})</option>
            ))}
          </select>
        </div>
        <textarea placeholder="Findings" value={reportFindings} onChange={(e) => setReportFindings(e.target.value)} rows={3} />
        <textarea placeholder="Impression" value={reportImpression} onChange={(e) => setReportImpression(e.target.value)} rows={2} />
        <textarea placeholder="Recommendation" value={reportRecommendation} onChange={(e) => setReportRecommendation(e.target.value)} rows={2} />
        <button type="submit" disabled={reportBusy}>{reportBusy ? 'Saving…' : 'Save Draft'}</button>
        {reportError && <p className="alert-error">{reportError}</p>}
        {reportSuccess && <p className="muted">{reportSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>Order</th><th>Findings</th><th>Impression</th><th>Status</th><th>Signed</th><th>Created</th></tr>
        </thead>
        <tbody>
          {(reports?.items ?? []).map((r) => (
            <tr key={r.id}>
              <td className="mono">{r.order_id.slice(0, 8)}…</td>
              <td>{r.findings?.slice(0, 40) ?? '—'}{r.findings && r.findings.length > 40 ? '…' : ''}</td>
              <td>{r.impression?.slice(0, 40) ?? '—'}{r.impression && r.impression.length > 40 ? '…' : ''}</td>
              <td>{r.status}</td>
              <td>{r.signed_at ? fmt(r.signed_at) : '—'}</td>
              <td>{fmt(r.created_at)}</td>
            </tr>
          ))}
          {(reports?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No reports.</td></tr>}
        </tbody>
      </table>
    </PanelShell>
  )
}
