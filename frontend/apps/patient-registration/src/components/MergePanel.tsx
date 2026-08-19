import { useState } from 'react'
import { patientApi } from '../lib/client'
import type { PatientSummary } from '../lib/types'

export function MergePanel({
  patients,
  onMerged,
}: {
  patients: PatientSummary[]
  onMerged: (message: string) => void
}) {
  const [survivor, setSurvivor] = useState('')
  const [duplicate, setDuplicate] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setError(null)
    if (!survivor || !duplicate) {
      setError('Select both records')
      return
    }
    if (survivor === duplicate) {
      setError('Survivor and duplicate must differ')
      return
    }
    try {
      await patientApi.merge(survivor, duplicate)
      onMerged(`Merged ${duplicate} into ${survivor}`)
      setSurvivor('')
      setDuplicate('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Merge failed')
    }
  }

  return (
    <section className="card">
      <h2>Merge records</h2>
      <div className="grid">
        <label>
          Survivor
          <select value={survivor} onChange={(e) => setSurvivor(e.target.value)}>
            <option value="">—</option>
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.mrn ?? p.id} · {p.first_name} {p.last_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Duplicate (will be deactivated)
          <select value={duplicate} onChange={(e) => setDuplicate(e.target.value)}>
            <option value="">—</option>
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.mrn ?? p.id} · {p.first_name} {p.last_name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="alert-error">{error}</p>}
      <button className="danger" onClick={submit}>
        Merge
      </button>
    </section>
  )
}