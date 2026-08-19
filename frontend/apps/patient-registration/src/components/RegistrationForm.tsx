import { FormEvent, useState } from 'react'
import { patientApi } from '../lib/client'
import type { RegisterPatient } from '../lib/types'
import { validateRegister } from '../lib/validation'

const emptyForm = (): RegisterPatient => ({
  first_name: '',
  last_name: '',
  gender: 'UNDISCLOSED',
  language_pref: 'en',
  identifiers: [],
  contacts: [],
  addresses: [],
  alerts: [],
  consents: [],
})

export function RegistrationForm({ onRegistered }: { onRegistered: (id: string) => void }) {
  const [form, setForm] = useState<RegisterPatient>(emptyForm)
  const [errors, setErrors] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const set = <K extends keyof RegisterPatient>(key: K, value: RegisterPatient[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const validationErrors = validateRegister(form)
    setErrors(validationErrors)
    if (validationErrors.length) return
    setSubmitting(true)
    setServerError(null)
    try {
      const payload: RegisterPatient = {
        ...form,
        national_identifier: form.national_identifier || undefined,
        emergency_contact: form.emergency_contact || undefined,
        insurance: form.insurance || undefined,
        identifiers: form.national_identifier
          ? [
              ...(form.identifiers ?? []),
              { identifier_type: 'NATIONAL_ID', identifier_value: form.national_identifier },
            ]
          : form.identifiers,
      }
      const created = await patientApi.register(payload)
      onRegistered(created.id)
      setForm(emptyForm())
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} className="card" noValidate>
      <h2>Register Patient</h2>

      {(errors.length > 0 || serverError) && (
        <div className="alert-error" role="alert">
          {serverError && <p>{serverError}</p>}
          <ul>{errors.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}

      <div className="grid">
        <label>
          First name *
          <input value={form.first_name} onChange={(e) => set('first_name', e.target.value)} required />
        </label>
        <label>
          Last name *
          <input value={form.last_name} onChange={(e) => set('last_name', e.target.value)} required />
        </label>
        <label>
          Other names
          <input value={form.other_names ?? ''} onChange={(e) => set('other_names', e.target.value)} />
        </label>
        <label>
          Date of birth
          <input
            type="date"
            value={form.date_of_birth ?? ''}
            onChange={(e) => set('date_of_birth', e.target.value || undefined)}
          />
        </label>
        <label>
          Gender
          <select value={form.gender} onChange={(e) => set('gender', e.target.value as RegisterPatient['gender'])}>
            <option value="UNDISCLOSED">Undisclosed</option>
            <option value="MALE">Male</option>
            <option value="FEMALE">Female</option>
            <option value="OTHER">Other</option>
          </select>
        </label>
        <label>
          Blood group
          <select value={form.blood_group ?? ''} onChange={(e) => set('blood_group', e.target.value || undefined)}>
            <option value="">—</option>
            {['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
        </label>
        <label>
          Nationality
          <input value={form.nationality ?? ''} onChange={(e) => set('nationality', e.target.value)} />
        </label>
        <label>
          National ID
          <input
            placeholder="123-456789-1"
            value={form.national_identifier ?? ''}
            onChange={(e) => set('national_identifier', e.target.value)}
          />
        </label>
      </div>

      <fieldset>
        <legend>Emergency contact</legend>
        <div className="grid">
          <label>
            Name
            <input
              value={form.emergency_contact?.name ?? ''}
              onChange={(e) =>
                set('emergency_contact', { relationship: 'OTHER', phone: '', ...form.emergency_contact, name: e.target.value })
              }
            />
          </label>
          <label>
            Relationship
            <input
              value={form.emergency_contact?.relationship ?? ''}
              onChange={(e) =>
                set('emergency_contact', { name: '', phone: '', ...form.emergency_contact, relationship: e.target.value })
              }
            />
          </label>
          <label>
            Phone
            <input
              placeholder="+2557..."
              value={form.emergency_contact?.phone ?? ''}
              onChange={(e) =>
                set('emergency_contact', { name: '', relationship: '', ...form.emergency_contact, phone: e.target.value })
              }
            />
          </label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Medical alerts</legend>
        {form.alerts!.map((alert, i) => (
          <div key={i} className="grid">
            <span>
              {alert.alert_type} · {alert.severity} · {alert.title}
              <button
                type="button"
                onClick={() => set('alerts', form.alerts!.filter((_, idx) => idx !== i))}
                className="link"
              >
                remove
              </button>
            </span>
          </div>
        ))}
        <button
          type="button"
          onClick={() =>
            set('alerts', [
              ...(form.alerts ?? []),
              { alert_type: 'ALLERGY', severity: 'HIGH', title: 'New alert' },
            ])
          }
          className="secondary"
        >
          + Add alert
        </button>
      </fieldset>

      <div className="actions">
        <button type="submit" disabled={submitting}>
          {submitting ? 'Registering…' : 'Register patient'}
        </button>
      </div>
    </form>
  )
}