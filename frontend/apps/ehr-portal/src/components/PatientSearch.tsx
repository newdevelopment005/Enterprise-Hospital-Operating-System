// Patient lookup: search the MPI by name/MRN/number and select a record.

import { useState } from 'react'

import { mpiApi } from '../lib/client'
import type { PatientSummary } from '../lib/types'

export function PatientSearch({ onSelected }: { onSelected: (patient: PatientSummary) => void }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<PatientSummary[]>([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const run = async (text: string) => {
    setQ(text)
    if (!text.trim()) {
      setResults([])
      setOpen(false)
      return
    }
    setBusy(true)
    try {
      const r = await mpiApi.search(text.trim())
      setResults(r.patients)
      setOpen(true)
    } catch {
      setResults([])
    } finally {
      setBusy(false)
    }
  }

  const pick = (p: PatientSummary) => {
    onSelected(p)
    setQ(`${p.first_name} ${p.last_name}${p.mrn ? ` [${p.mrn}]` : ''}`)
    setOpen(false)
  }

  return (
    <div className="patient-search">
      <input
        placeholder="Search patient by name, MRN or number…"
        value={q}
        onChange={(e) => void run(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {busy && <span className="muted search-hint">Searching…</span>}
      {open && (
        <ul className="search-results">
          {results.length === 0 && <li className="muted">No matching patients</li>}
          {results.map((p) => (
            <li key={p.id} onMouseDown={() => pick(p)}>
              <strong>
                {p.first_name} {p.last_name}
              </strong>
              <span className="muted">
                {p.mrn ?? ''} {p.patient_number ? `· ${p.patient_number}` : ''} · {p.gender ?? '—'} ·{' '}
                {p.date_of_birth ?? '—'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}