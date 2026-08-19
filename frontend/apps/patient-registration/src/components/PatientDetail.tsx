import { FormEvent, useState } from 'react'
import { patientApi } from '../lib/client'
import type { MedicalAlert, PatientDetail, TimelineEntry } from '../lib/types'

const exploreAlert: MedicalAlert = { alert_type: 'ALLERGY', severity: 'HIGH', title: '', description: '' }

export function PatientDetailView({
  patient,
  onClose,
  onChanged,
}: {
  patient: PatientDetail
  onClose: () => void
  onChanged: () => void
}) {
  const [timeline, setTimeline] = useState<TimelineEntry[] | null>(null)
  const [timelineError, setTimelineError] = useState<string | null>(null)
  const [alertForm, setAlertForm] = useState<MedicalAlert>(exploreAlert)
  const [adding, setAdding] = useState(false)
  const [alertError, setAlertError] = useState<string | null>(null)

  const loadTimeline = async () => {
    setTimelineError(null)
    try {
      setTimeline(await patientApi.timeline(patient.id))
    } catch (err) {
      setTimelineError(err instanceof Error ? err.message : 'Timeline failed')
    }
  }

  const submitAlert = async (e: FormEvent) => {
    e.preventDefault()
    setAdding(true)
    setAlertError(null)
    try {
      await patientApi.addAlert(patient.id, alertForm)
      setAlertForm(exploreAlert)
      onChanged()
      await loadTimeline()
    } catch (err) {
      setAlertError(err instanceof Error ? err.message : 'Failed to add alert')
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="card">
      <div className="detail-head">
        <h2>
          {patient.first_name} {patient.last_name}
        </h2>
        <button className="link" onClick={onClose}>
          close
        </button>
      </div>
      <p className="muted">
        {[patient.mrn, patient.patient_number, `#${patient.id}`].filter(Boolean).join(' · ')}
      </p>

      <div className="grid">
        <span>{patient.date_of_birth ?? 'DOB unknown'}</span>
        <span>{patient.gender}</span>
        <span>{patient.nationality}</span>
        <span>{patient.biometrics_ready ? 'Biometrics ready' : 'No biometrics'}</span>
      </div>

      {patient.emergency_contact && (
        <p>
          Emergency: <strong>{patient.emergency_contact.name}</strong> ({patient.emergency_contact.relationship}) ·{' '}
          {patient.emergency_contact.phone}
        </p>
      )}

      <form onSubmit={submitAlert} className="inline-form">
        <input
          placeholder="Alert title (e.g. Penicillin allergy)"
          value={alertForm.title}
          onChange={(e) => setAlertForm({ ...alertForm, title: e.target.value })}
        />
        <select
          value={alertForm.severity}
          onChange={(e) => setAlertForm({ ...alertForm, severity: e.target.value as MedicalAlert['severity'] })}
        >
          {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={alertForm.alert_type}
          onChange={(e) =>
            setAlertForm({ ...alertForm, alert_type: e.target.value as MedicalAlert['alert_type'] })
          }
        >
          {['ALLERGY', 'CONDITION', 'FALL_RISK', 'DRUG_SENSITIVITY', 'INFECTION', 'OTHER'].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button type="submit" disabled={adding || !alertForm.title.trim()}>
          {adding ? '…' : 'Add alert'}
        </button>
      </form>
      {alertError && <p className="alert-error">{alertError}</p>}

      <h3>Timeline</h3>
      <button className="secondary" onClick={loadTimeline}>
        {timeline ? 'Refresh' : 'Load timeline'}
      </button>
      {timelineError && <p className="alert-error">{timelineError}</p>}
      {timeline && (
        <ul className="timeline">
          {timeline.map((entry) => (
            <li key={entry.id}>
              <span className="muted">{entry.occurred_at.split('T')[0]}</span>{' '}
              <strong>{entry.event_type}</strong> {entry.source && <span className="muted">({entry.source})</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}