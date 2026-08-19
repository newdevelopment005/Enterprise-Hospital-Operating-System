import { FormEvent, useEffect, useState } from 'react'
import { patientApi } from '../lib/client'
import type { PatientSummary } from '../lib/types'
import { validateSearchQuery } from '../lib/validation'

export function PatientSearch({
  onOpen,
  onLoaded,
}: {
  onOpen: (id: string) => void
  onLoaded?: (patients: PatientSummary[]) => void
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PatientSummary[]>([])
  const [total, setTotal] = useState(0)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (e?: FormEvent) => {
    e?.preventDefault()
    const invalid = validateSearchQuery(query)
    setError(invalid)
    if (invalid) return
    setSearching(true)
    try {
      const result = await patientApi.search(query || '')
      setResults(result.patients)
      setTotal(result.total)
      onLoaded?.(result.patients)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setSearching(false)
    }
  }

  useEffect(() => {
    void run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <section className="card">
      <h2>Patient search</h2>
      <form onSubmit={run} className="search-row">
        <input
          placeholder="Name, MRN, number or National ID…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="submit" disabled={searching}>
          {searching ? '…' : 'Search'}
        </button>
      </form>
      {error && <p className="alert-error">{error}</p>}
      <p className="muted">{total} result(s)</p>
      <table>
        <thead>
          <tr>
            <th>MRN</th>
            <th>Name</th>
            <th>DOB</th>
            <th>Gender</th>
            <th>Biometrics</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {results.map((p) => (
            <tr key={p.id}>
              <td>{p.mrn ?? '—'}</td>
              <td>
                {p.first_name} {p.last_name}
              </td>
              <td>{p.date_of_birth ?? '—'}</td>
              <td>{p.gender}</td>
              <td>{p.biometrics_ready ? '✓' : '—'}</td>
              <td>
                <button className="link" onClick={() => onOpen(p.id)}>
                  open
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}