// Patient identity & demographics panel backed by the patient-service (MPI).

import type { ReactNode } from 'react'

import { mpiApi } from '../lib/client'
import type { PatientDetail } from '../lib/types'
import { fmt, PanelShell, useLoad } from './Panels'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="info-section">
      <h4>{title}</h4>
      {children}
    </section>
  )
}

function KeyVal({ k, v }: { k: string; v?: unknown }) {
  const text =
    v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0) ? '—' : String(v)
  return (
    <div className="kv">
      <dt>{k}</dt>
      <dd>{text}</dd>
    </div>
  )
}

// contact_info / address / emergency_contact are stored as JSON in the MPI.
// Depending on how the record was created they can be a single object or a list.
function toList(value: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(value)) return value as Array<Record<string, unknown>>
  if (value && typeof value === 'object') return [value as Record<string, unknown>]
  return []
}

export function InfoPanel({ patientId }: { patientId: string }) {
  const { data, error } = useLoad<PatientDetail>(() => mpiApi.get(patientId))

  return (
    <PanelShell title="Demographics & Identity" error={error}>
      {data && (
        <div className="info-grid">
          <Section title="Identity">
            <dl className="kv-list">
              <KeyVal k="Full name" v={`${data.first_name} ${data.last_name}`} />
              <KeyVal k="Other names" v={data.other_names} />
              <KeyVal k="MRN" v={data.mrn} />
              <KeyVal k="Patient number" v={data.patient_number} />
              <KeyVal k="Date of birth" v={data.date_of_birth} />
              <KeyVal k="Gender" v={data.gender} />
              <KeyVal k="Blood group" v={data.blood_group} />
              <KeyVal k="Nationality" v={data.nationality} />
              <KeyVal k="Marital status" v={data.marital_status} />
              <KeyVal k="Language" v={data.language_pref} />
              <KeyVal k="Registered" v={data.registration_date} />
              <KeyVal k="Biometrics ready" v={data.biometrics_ready ? 'Yes' : 'No'} />
            </dl>
          </Section>

          <Section title="Contacts">
            {toList(data.contact_info).length === 0 ? (
              <p className="muted">No contacts recorded.</p>
            ) : (
              toList(data.contact_info).map((c, i) => (
                <div key={i} className="entry">
                  <dl className="kv-list">
                    {Object.entries(c).map(([k, v]) => (
                      <KeyVal key={k} k={k.replace(/_/g, ' ')} v={v} />
                    ))}
                  </dl>
                </div>
              ))
            )}
          </Section>

          <Section title="Addresses">
            {toList(data.address).length === 0 ? (
              <p className="muted">No addresses recorded.</p>
            ) : (
              toList(data.address).map((a, i) => (
                <div key={i} className="entry">
                  <dl className="kv-list">
                    {Object.entries(a).map(([k, v]) => (
                      <KeyVal key={k} k={k.replace(/_/g, ' ')} v={v} />
                    ))}
                  </dl>
                </div>
              ))
            )}
          </Section>

          <Section title="Emergency Contact">
            {data.emergency_contact ? (
              <dl className="kv-list">
                {Object.entries(data.emergency_contact).map(([k, v]) => (
                  <KeyVal key={k} k={k.replace(/_/g, ' ')} v={v} />
                ))}
              </dl>
            ) : (
              <p className="muted">No emergency contact recorded.</p>
            )}
          </Section>

          <Section title="Consent">
            {data.consent_summary ? (
              <dl className="kv-list">
                {Object.entries(data.consent_summary).map(([k, v]) => (
                  <KeyVal key={k} k={k.replace(/_/g, ' ')} v={v} />
                ))}
              </dl>
            ) : (
              <p className="muted">No consent summary recorded.</p>
            )}
          </Section>

          <Section title="Record">
            <dl className="kv-list">
              <KeyVal k="Internal UUID" v={data.id} />
              <KeyVal k="Merged into" v={data.merged_into_id} />
              <KeyVal k="Created" v={fmt(data.created_at)} />
              <KeyVal k="Deceased" v={data.deceased_at ? fmt(data.deceased_at) : 'No'} />
            </dl>
          </Section>
        </div>
      )}
    </PanelShell>
  )
}