// Insurance panel: coverages, claims, prior authorizations for a patient.

import { FormEvent, useState } from 'react'
import { insuranceApi } from '../lib/client'
import type { Claim, Coverage, CoverageCreate, PriorAuth } from '../lib/types'
import { PanelShell, fmt, useLoad } from './Panels'

const COVERAGE_TYPES = ['HEALTH', 'DENTAL', 'VISION', 'PRESCRIPTION', 'MENTAL_HEALTH']

export function InsurancePanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const { data: coverages, reload: reloadCoverages } = useLoad(() => insuranceApi.listCoverages(patientId))
  const { data: claims, reload: reloadClaims } = useLoad(() => insuranceApi.listClaims(patientId))
  const { data: priorAuths, reload: reloadPriorAuths } = useLoad(() => insuranceApi.listPriorAuths(patientId))

  // Create coverage form
  const [payerName, setPayerName] = useState('')
  const [planName, setPlanName] = useState('')
  const [policyNumber, setPolicyNumber] = useState('')
  const [coverageType, setCoverageType] = useState('HEALTH')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [covBusy, setCovBusy] = useState(false)
  const [covError, setCovError] = useState<string | null>(null)
  const [covSuccess, setCovSuccess] = useState<string | null>(null)

  // Create claim form
  const [claimCoverage, setClaimCoverage] = useState('')
  const [serviceDate, setServiceDate] = useState('')
  const [totalAmount, setTotalAmount] = useState('0')
  const [procCodes, setProcCodes] = useState('')
  const [claimBusy, setClaimBusy] = useState(false)
  const [claimError, setClaimError] = useState<string | null>(null)
  const [claimSuccess, setClaimSuccess] = useState<string | null>(null)

  // Create prior auth form
  const [paCoverage, setPaCoverage] = useState('')
  const [serviceType, setServiceType] = useState('')
  const [justification, setJustification] = useState('')
  const [paBusy, setPaBusy] = useState(false)
  const [paError, setPaError] = useState<string | null>(null)
  const [paSuccess, setPaSuccess] = useState<string | null>(null)

  const handleCreateCoverage = async (e: FormEvent) => {
    e.preventDefault()
    if (!payerName.trim() || !policyNumber.trim() || !effectiveDate) return
    setCovBusy(true)
    setCovError(null)
    setCovSuccess(null)
    try {
      const payload: CoverageCreate = {
        patient_id: patientId,
        payer_name: payerName.trim(),
        plan_name: planName.trim() || undefined,
        policy_number: policyNumber.trim(),
        coverage_type: coverageType,
        effective_date: effectiveDate,
        is_active: true,
      }
      await insuranceApi.createCoverage(payload)
      setCovSuccess('Coverage added')
      setPayerName('')
      setPlanName('')
      setPolicyNumber('')
      await reloadCoverages()
    } catch (err) {
      setCovError(err instanceof Error ? err.message : 'Failed to add coverage')
    } finally {
      setCovBusy(false)
    }
  }

  const handleCreateClaim = async (e: FormEvent) => {
    e.preventDefault()
    if (!claimCoverage || !serviceDate) return
    setClaimBusy(true)
    setClaimError(null)
    setClaimSuccess(null)
    try {
      await insuranceApi.createClaim({
        patient_id: patientId,
        coverage_id: claimCoverage,
        service_date: serviceDate,
        procedure_codes: procCodes.split(',').map((s) => s.trim()).filter(Boolean) || undefined,
        total_amount: Number(totalAmount) || 0,
      })
      setClaimSuccess('Claim created')
      setServiceDate('')
      setTotalAmount('0')
      setProcCodes('')
      await reloadClaims()
    } catch (err) {
      setClaimError(err instanceof Error ? err.message : 'Failed to create claim')
    } finally {
      setClaimBusy(false)
    }
  }

  const handleCreatePriorAuth = async (e: FormEvent) => {
    e.preventDefault()
    if (!paCoverage || !serviceType.trim()) return
    setPaBusy(true)
    setPaError(null)
    setPaSuccess(null)
    try {
      await insuranceApi.createPriorAuth({
        patient_id: patientId,
        coverage_id: paCoverage,
        service_type: serviceType.trim(),
        clinical_justification: justification.trim() || undefined,
        requested_by: authorId,
      })
      setPaSuccess('Prior authorization requested')
      setServiceType('')
      setJustification('')
      await reloadPriorAuths()
    } catch (err) {
      setPaError(err instanceof Error ? err.message : 'Failed to request prior authorization')
    } finally {
      setPaBusy(false)
    }
  }

  const handleSubmitClaim = async (claimId: string) => {
    try {
      await insuranceApi.submitClaim(claimId)
      await reloadClaims()
    } catch (err) {
      setClaimError(err instanceof Error ? err.message : 'Failed to submit claim')
    }
  }

  const handleApproveAuth = async (paId: string) => {
    try {
      await insuranceApi.decidePriorAuth(paId, { decision: 'APPROVED', decided_by: authorId })
      await reloadPriorAuths()
    } catch (err) {
      setPaError(err instanceof Error ? err.message : 'Failed to approve authorization')
    }
  }

  const coverageName = (id: string) => coverages?.items?.find((c: Coverage) => c.id === id)?.payer_name ?? '?'

  return (
    <PanelShell
      title="Insurance"
      addForm={
        <form onSubmit={handleCreateCoverage} className="grid">
          <input placeholder="Payer name" value={payerName} onChange={(e) => setPayerName(e.target.value)} />
          <input placeholder="Policy number" value={policyNumber} onChange={(e) => setPolicyNumber(e.target.value)} />
          <input placeholder="Plan name" value={planName} onChange={(e) => setPlanName(e.target.value)} />
          <select value={coverageType} onChange={(e) => setCoverageType(e.target.value)}>
            {COVERAGE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input type="date" placeholder="Effective date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} />
          <button type="submit" disabled={covBusy}>{covBusy ? 'Adding…' : 'Add Coverage'}</button>
          {covError && <p className="alert-error">{covError}</p>}
          {covSuccess && <p className="muted">{covSuccess}</p>}
        </form>
      }
    >
      {/* Coverages */}
      <h3>Coverages — this patient</h3>
      <table>
        <thead>
          <tr><th>Payer</th><th>Plan</th><th>Policy</th><th>Type</th><th>Effective</th><th>Active</th></tr>
        </thead>
        <tbody>
          {(coverages?.items ?? []).map((c: Coverage) => (
            <tr key={c.id}>
              <td>{c.payer_name}</td>
              <td>{c.plan_name ?? '—'}</td>
              <td className="mono">{c.policy_number}</td>
              <td>{c.coverage_type}</td>
              <td>{c.effective_date}</td>
              <td>{c.is_active ? '✓' : '✗'}</td>
            </tr>
          ))}
          {(coverages?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No coverages for this patient.</td></tr>}
        </tbody>
      </table>

      {/* Claims */}
      <h3>Claims — this patient</h3>
      <form onSubmit={handleCreateClaim} className="card">
        <h4>Create claim</h4>
        <div className="grid">
          <select value={claimCoverage} onChange={(e) => setClaimCoverage(e.target.value)}>
            <option value="">— Select coverage —</option>
            {(coverages?.items ?? []).filter((c: Coverage) => c.is_active).map((c: Coverage) => (
              <option key={c.id} value={c.id}>{c.payer_name} ({c.policy_number})</option>
            ))}
          </select>
          <input type="date" placeholder="Service date" value={serviceDate} onChange={(e) => setServiceDate(e.target.value)} />
          <input type="number" step="0.01" placeholder="Total amount" value={totalAmount} onChange={(e) => setTotalAmount(e.target.value)} />
          <input placeholder="Procedure codes (comma-separated)" value={procCodes} onChange={(e) => setProcCodes(e.target.value)} />
        </div>
        <button type="submit" disabled={claimBusy}>{claimBusy ? 'Creating…' : 'Create Claim'}</button>
        {claimError && <p className="alert-error">{claimError}</p>}
        {claimSuccess && <p className="muted">{claimSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>ID</th><th>Coverage</th><th>Service date</th><th>Total</th><th>Status</th><th>Submitted</th><th></th></tr>
        </thead>
        <tbody>
          {(claims?.items ?? []).map((cl: Claim) => (
            <tr key={cl.id}>
              <td className="mono">{cl.id.slice(0, 8)}…</td>
              <td>{coverageName(cl.coverage_id)}</td>
              <td>{cl.service_date}</td>
              <td className="mono">${cl.total_amount}</td>
              <td>{cl.status}</td>
              <td>{fmt(cl.submitted_at ?? undefined)}</td>
              <td>
                {cl.status === 'DRAFT' && <button onClick={() => handleSubmitClaim(cl.id)}>Submit</button>}
              </td>
            </tr>
          ))}
          {(claims?.items?.length ?? 0) === 0 && <tr><td colSpan={7} className="muted">No claims for this patient.</td></tr>}
        </tbody>
      </table>

      {/* Prior authorizations */}
      <h3>Prior Authorizations — this patient</h3>
      <form onSubmit={handleCreatePriorAuth} className="card">
        <h4>Request authorization</h4>
        <div className="grid">
          <select value={paCoverage} onChange={(e) => setPaCoverage(e.target.value)}>
            <option value="">— Select coverage —</option>
            {(coverages?.items ?? []).filter((c: Coverage) => c.is_active).map((c: Coverage) => (
              <option key={c.id} value={c.id}>{c.payer_name} ({c.policy_number})</option>
            ))}
          </select>
          <input placeholder="Service type (e.g. MRI)" value={serviceType} onChange={(e) => setServiceType(e.target.value)} />
          <input placeholder="Clinical justification" value={justification} onChange={(e) => setJustification(e.target.value)} />
        </div>
        <button type="submit" disabled={paBusy}>{paBusy ? 'Requesting…' : 'Request Authorization'}</button>
        {paError && <p className="alert-error">{paError}</p>}
        {paSuccess && <p className="muted">{paSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>Coverage</th><th>Service</th><th>Status</th><th>Decision</th><th>Requested</th><th></th></tr>
        </thead>
        <tbody>
          {(priorAuths?.items ?? []).map((pa: PriorAuth) => (
            <tr key={pa.id}>
              <td>{coverageName(pa.coverage_id)}</td>
              <td>{pa.service_type}</td>
              <td>{pa.status}</td>
              <td>{pa.decision ?? '—'}</td>
              <td>{fmt(pa.created_at)}</td>
              <td>
                {pa.status === 'PENDING' && <button onClick={() => handleApproveAuth(pa.id)}>Approve</button>}
              </td>
            </tr>
          ))}
          {(priorAuths?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No authorizations requested.</td></tr>}
        </tbody>
      </table>
    </PanelShell>
  )
}