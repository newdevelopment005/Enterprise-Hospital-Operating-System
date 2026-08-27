// Appointments panel: book, reschedule, cancel, complete — hits appointment-service.

import { FormEvent, useState } from 'react'
import { appointmentsApi } from '../lib/client'
import type { Appointment } from '../lib/types'
import { PanelShell, fmt, useLoad } from './Panels'

const TYPES = ['OUTPATIENT', 'FOLLOWUP', 'PROCEDURE', 'TELEHEALTH']
const PRIORITIES = ['ROUTINE', 'URGENT', 'EMERGENCY']

function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function AppointmentsPanel({ patientId }: { patientId: string }) {
  const [upcomingOnly, setUpcomingOnly] = useState(true)
  const { data, error, reload } = useLoad(() => appointmentsApi.list(patientId, upcomingOnly))

  // booking form state
  const [type, setType] = useState('OUTPATIENT')
  const [priority, setPriority] = useState('ROUTINE')
  const [start, setStart] = useState('')
  const [duration, setDuration] = useState('30')
  const [providerId, setProviderId] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // row actions
  const [rescheduling, setRescheduling] = useState<string | null>(null)
  const [newStart, setNewStart] = useState('')

  const book = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setFormError(null)
    try {
      if (!start) throw new Error('Pick a date and time')
      await appointmentsApi.book({
        patient_id: patientId,
        appointment_type: type,
        priority,
        start_time: new Date(start).toISOString(),
        duration_min: Number(duration) || undefined,
        provider_id: providerId || undefined,
        reason: reason || undefined,
      })
      setStart(''); setReason(''); setProviderId('')
      await reload()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to book appointment')
    } finally {
      setBusy(false)
    }
  }

  const act = async (fn: () => Promise<unknown>) => {
    setFormError(null)
    try {
      await fn()
      await reload()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Action failed')
    }
  }

  return (
    <PanelShell
      title="Appointments"
      error={error ?? formError}
      addForm={
        <form onSubmit={book} className="stack">
          <div className="grid">
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <select value={priority} onChange={(e) => setPriority(e.target.value)}>
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div className="grid">
            <label>
              Date &amp; time
              <input type="datetime-local" value={start} min={toLocalInput(new Date())} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label>
              Duration (min)
              <input type="number" min={5} max={480} step={5} value={duration} onChange={(e) => setDuration(e.target.value)} />
            </label>
          </div>
          <div className="grid">
            <label>
              Provider UUID (optional)
              <input placeholder="Provider UUID (optional)" value={providerId} onChange={(e) => setProviderId(e.target.value.trim())} />
            </label>
            <label>
              Reason
              <input placeholder="Reason for visit" value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          </div>
          {formError && <p className="alert-error">{formError}</p>}
          <button type="submit" disabled={busy}>{busy ? 'Booking…' : 'Book appointment'}</button>
        </form>
      }
    >
      <label style={{ display: 'block', marginBottom: '0.5rem' }}>
        <input
          type="checkbox"
          checked={upcomingOnly}
          onChange={(e) => setUpcomingOnly(e.target.checked)}
        />{' '}
        Upcoming only
      </label>
      <table>
        <thead>
          <tr><th>When</th><th>Type</th><th>Status</th><th>Priority</th><th>Reason</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {(data?.appointments ?? []).map((a: Appointment) => (
            <tr key={a.id}>
              <td>{fmt(a.start_time)}{a.duration_min ? ` · ${a.duration_min}m` : ''}</td>
              <td>{a.appointment_type}</td>
              <td>{a.status}</td>
              <td>{a.priority}</td>
              <td className="clamp">{a.cancellation_reason || a.reason || '—'}</td>
              <td>
                {['SCHEDULED', 'REQUESTED', 'ARRIVED', 'IN_PROGRESS'].includes(a.status) && (
                  <>
                    {rescheduling === a.id ? (
                      <>
                        <input
                          type="datetime-local"
                          value={newStart}
                          min={toLocalInput(new Date())}
                          onChange={(e) => setNewStart(e.target.value)}
                        />{' '}
                        <button
                          onClick={() =>
                            act(async () => {
                              if (!newStart) throw new Error('Pick a new time')
                              await appointmentsApi.reschedule(a.id, new Date(newStart).toISOString())
                              setRescheduling(null); setNewStart('')
                            })
                          }
                        >
                          Save
                        </button>{' '}
                        <button onClick={() => { setRescheduling(null); setNewStart('') }}>✕</button>
                      </>
                    ) : (
                      <button onClick={() => { setRescheduling(a.id); setNewStart(toLocalInput(new Date(a.start_time))) }}>
                        Reschedule
                      </button>
                    )}{' '}
                    <button onClick={() => act(() => appointmentsApi.cancel(a.id))}>Cancel</button>{' '}
                    <button onClick={() => act(() => appointmentsApi.complete(a.id))}>Complete</button>{' '}
                    <button onClick={() => act(() => appointmentsApi.noShow(a.id))}>No-show</button>
                  </>
                )}
              </td>
            </tr>
          ))}
          {(data?.appointments?.length ?? 0) === 0 && (
            <tr><td colSpan={6} className="muted">No appointments found.</td></tr>
          )}
        </tbody>
      </table>
    </PanelShell>
  )
}
