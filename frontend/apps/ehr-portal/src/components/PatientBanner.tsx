// Patient header banner: demographics snapshot + active medical alerts.

import { useEffect, useState } from 'react'

import { mpiApi } from '../lib/client'
import type { MedicalAlert, PatientDetail } from '../lib/types'

const SEVERITY_CLASS: Record<string, string> = {
  LOW: 'sev-low',
  MEDIUM: 'sev-medium',
  HIGH: 'sev-high',
  CRITICAL: 'sev-critical',
}

function age(dob?: string | null): string {
  if (!dob) return '—'
  const birth = new Date(dob)
  const now = new Date()
  let a = now.getFullYear() - birth.getFullYear()
  const ahead = now.getMonth() - birth.getMonth()
  if (ahead < 0 || (ahead === 0 && now.getDate() < birth.getDate())) a -= 1
  return a >= 0 ? `${a} yrs` : '—'
}

export function PatientBanner({ patientId }: { patientId: string }) {
  const [detail, setDetail] = useState<PatientDetail | null>(null)
  const [alerts, setAlerts] = useState<MedicalAlert[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setDetail(null)
    setAlerts([])
    setError(null)
    Promise.all([mpiApi.get(patientId), mpiApi.alerts(patientId, true)])
      .then(([d, a]) => {
        if (cancelled) return
        setDetail(d)
        setAlerts(a.items)
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load patient')
      })
    return () => {
      cancelled = true
    }
  }, [patientId])

  if (error) return <div className="alert-error">Could not load patient details: {error}</div>
  if (!detail) return <div className="banner loading">Loading patient…</div>

  return (
    <div className="banner">
      <div className="banner-main">
        <h2>
          {detail.first_name} {detail.last_name}
          {detail.other_names ? ` (${detail.other_names})` : ''}
        </h2>
        <div className="badges">
          {detail.mrn && <span className="badge">MRN {detail.mrn}</span>}
          {detail.patient_number && <span className="badge">{detail.patient_number}</span>}
          <span className="badge">{detail.gender ?? '—'}, {age(detail.date_of_birth)}</span>
          {detail.blood_group && <span className="badge blood">O+ · {detail.blood_group}</span>}
        </div>
      </div>

      <dl className="banner-facts">
        <div>
          <dt>DOB</dt>
          <dd>{detail.date_of_birth ?? '—'}</dd>
        </div>
        <div>
          <dt>Nationality</dt>
          <dd>{detail.nationality ?? '—'}</dd>
        </div>
        <div>
          <dt>Language</dt>
          <dd>{detail.language_pref ? detail.language_pref.toUpperCase() : '—'}</dd>
        </div>
        <div>
          <dt>Marital</dt>
          <dd>{detail.marital_status ?? '—'}</dd>
        </div>
        <div>
          <dt>Registered</dt>
          <dd>{detail.registration_date ?? '—'}</dd>
        </div>
      </dl>

      {alerts.length > 0 && (
        <div className="alerts">
          {alerts.map((a) => (
            <span key={a.id} className={`alert-chip ${SEVERITY_CLASS[a.severity] ?? ''}`} title={a.description ?? a.title}>
              {a.alert_type}: {a.title}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}