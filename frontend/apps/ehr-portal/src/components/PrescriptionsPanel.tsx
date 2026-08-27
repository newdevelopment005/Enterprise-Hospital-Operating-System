// Prescriptions panel: prescribe with allergy safety, allergies list, lifecycle.

import { FormEvent, useState } from 'react'
import { prescriptionsApi } from '../lib/client'
import type { PatientAllergy, Prescription, PrescriptionIn, RxItemIn } from '../lib/types'
import { PanelShell, fmt, useLoad } from './Panels'

const THERAPY_TYPES = ['ACUTE', 'CHRONIC', 'PRN', 'PROPHYLACTIC']
const ALLERGY_TYPES = ['DRUG', 'FOOD', 'ENVIRONMENT', 'OTHER']
const SEVERITIES = ['MILD', 'MODERATE', 'SEVERE']

export function PrescriptionsPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const { data, error, reload } = useLoad(() => prescriptionsApi.list(patientId))
  const { data: allergies, reload: reloadAllergies } = useLoad(() => prescriptionsApi.allergies(patientId))

  // prescription form
  const [therapyType, setTherapyType] = useState('ACUTE')
  const [medication, setMedication] = useState('')
  const [dosage, setDosage] = useState('')
  const [frequency, setFrequency] = useState('')
  const [route, setRoute] = useState('ORAL')
  const [duration, setDuration] = useState('7')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [overrideNext, setOverrideNext] = useState(false)

  // allergy form
  const [allergen, setAllergen] = useState('')
  const [allergyType, setAllergyType] = useState('DRUG')
  const [severity, setSeverity] = useState('MODERATE')

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setFormError(null)
    try {
      if (!medication.trim() || !dosage.trim() || !frequency.trim()) {
        throw new Error('Medication, dosage and frequency are required')
      }
      const item: RxItemIn = {
        medication: medication.trim(),
        dosage: dosage.trim(),
        frequency: frequency.trim(),
        route: route || undefined,
        duration_days: Number(duration) || undefined,
      }
      const payload: PrescriptionIn = {
        patient_id: patientId,
        prescriber_id: authorId,
        therapy_type: therapyType,
        reason: reason || undefined,
        items: [item],
        override_flags: overrideNext || undefined,
      }
      await prescriptionsApi.create(payload)
      setMedication(''); setDosage(''); setFrequency(''); setReason(''); setOverrideNext(false)
      await Promise.all([reload(), reloadAllergies()])
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to prescribe'
      setFormError(msg.includes('ALLERGY_CONFLICT') || msg.includes('Allergy conflict')
        ? `${msg} — tick "override" to prescribe anyway.`
        : msg)
    } finally {
      setBusy(false)
    }
  }

  const addAllergy = async (e: FormEvent) => {
    e.preventDefault()
    if (!allergen.trim()) return
    try {
      await prescriptionsApi.addAllergy(patientId, {
        allergen: allergen.trim(),
        allergen_type: allergyType,
        severity,
        recorded_by: authorId,
      })
      setAllergen('')
      await reloadAllergies()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to record allergy')
    }
  }

  return (
    <PanelShell
      title="Prescriptions"
      error={error ?? formError}
      addForm={
        <form onSubmit={create} className="stack">
          <div className="grid">
            <select value={therapyType} onChange={(e) => setTherapyType(e.target.value)}>
              {THERAPY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input placeholder="Medication (e.g. Paracetamol 500mg)" value={medication} onChange={(e) => setMedication(e.target.value)} />
          </div>
          <div className="grid">
            <input placeholder="Dosage (e.g. 1 tablet)" value={dosage} onChange={(e) => setDosage(e.target.value)} />
            <input placeholder="Frequency (e.g. 3 times daily)" value={frequency} onChange={(e) => setFrequency(e.target.value)} />
            <input placeholder="Route (ORAL/IV/…)" value={route} onChange={(e) => setRoute(e.target.value)} />
            <label>
              Days
              <input type="number" min={1} max={365} value={duration} onChange={(e) => setDuration(e.target.value)} />
            </label>
          </div>
          <input placeholder="Clinical reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
          <label style={{ display: 'block' }}>
            <input type="checkbox" checked={overrideNext} onChange={(e) => setOverrideNext(e.target.checked)} />{' '}
            Override allergy conflict (recorded on the audit trail)
          </label>
          {formError && <p className="alert-error">{formError}</p>}
          <button type="submit" disabled={busy}>{busy ? 'Prescribing…' : 'Prescribe'}</button>
        </form>
      }
    >
      {/* drug allergies drive the prescribing safety check */}
      <form onSubmit={addAllergy} className="grid" style={{ marginBottom: '0.75rem' }}>
        <input placeholder="Add patient allergy (e.g. Penicillin)" value={allergen} onChange={(e) => setAllergen(e.target.value)} />
        <select value={allergyType} onChange={(e) => setAllergyType(e.target.value)}>
          {ALLERGY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
          {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button type="submit">Record</button>
      </form>

      {(allergies?.items?.length ?? 0) > 0 && (
        <p className="muted" style={{ marginBottom: '0.5rem' }}>
          Allergies: {(allergies!.items as PatientAllergy[]).map((a) => `${a.allergen} (${a.severity})`).join(', ')}
        </p>
      )}

      <table>
        <thead>
          <tr><th>Issued</th><th>Type</th><th>Items</th><th>Status</th><th>Notes</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {(data?.prescriptions ?? []).map((rx: Prescription) => (
            <tr key={rx.id}>
              <td>{fmt(rx.issue_date)}</td>
              <td>{rx.therapy_type}</td>
              <td className="clamp">{(rx.items ?? []).map((i) => i.medication).join(', ') || '—'}</td>
              <td>{rx.status}</td>
              <td className="clamp">{rx.cancellation_reason || rx.audit_reference || rx.reason || '—'}</td>
              <td>
                {['ACTIVE', 'PAUSED'].includes(rx.status) && (
                  <>
                    <button onClick={() => void prescriptionsApi.cancel(rx.id, 'Cancelled by clinician').then(reload)}>
                      Cancel
                    </button>{' '}
                    <button onClick={() => void prescriptionsApi.complete(rx.id).then(reload)}>Complete</button>
                  </>
                )}
              </td>
            </tr>
          ))}
          {(data?.prescriptions?.length ?? 0) === 0 && (
            <tr><td colSpan={6} className="muted">No prescriptions for this patient.</td></tr>
          )}
        </tbody>
      </table>
    </PanelShell>
  )
}
