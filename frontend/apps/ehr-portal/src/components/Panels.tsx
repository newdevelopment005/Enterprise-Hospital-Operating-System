// Clinical module panels: each is a list + add form hitting one module endpoint.

import { FormEvent, ReactNode, useCallback, useEffect, useState } from 'react'
import {
  ehrApi,
} from '../lib/client'
import type {
  Allergy,
  ClinicalNote,
  ClinicalOrder,
  Diagnosis,
  Encounter,
  MedicalHistoryEntry,
  Medication,
  Problem,
  Vital,
} from '../lib/types'

export const DEFAULT_AUTHOR = '22222222-2222-2222-2222-222222222222'

export function useLoad<T>(loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await loader())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }, [loader])
  useEffect(() => {
    void reload()
  }, [reload])
  return { data, error, loading, reload }
}

export function PanelShell({ title, addForm, error, children }: {
  title: string
  addForm?: ReactNode
  error?: string | null
  children: ReactNode
}) {
  return (
    <div className="card">
      <h3>{title}</h3>
      {error && <p className="alert-error">{error}</p>}
      {addForm}
      {children}
    </div>
  )
}

export function fmt(ts?: string): string {
  return ts ? ts.replace('T', ' ').slice(0, 16) : '—'
}

// ------------------------------------------------------------------ Notes

export function NotesPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const [noteType, setNoteType] = useState('SOAP')
  const [content, setContent] = useState('')
  const [subject, setSubject] = useState('')
  const [objective, setObjective] = useState('')
  const [assessment, setAssessment] = useState('')
  const [plan, setPlan] = useState('')
  const [filter, setFilter] = useState<string | undefined>(undefined)
  const { data, error, reload } = useLoad(() => ehrApi.listNotes(patientId, filter))
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setFormError(null)
    try {
      if (noteType === 'SOAP') {
        await ehrApi.createSoap(patientId, {
          subjective: subject, objective, assessment, plan,
          author_id: authorId,
        })
      } else if (noteType === 'PROGRESS') {
        await ehrApi.createProgress(patientId, { content, author_id: authorId })
      } else if (noteType === 'DISCHARGE') {
        await ehrApi.createDischarge(patientId, { summary: content, author_id: authorId })
      } else {
        await ehrApi.createNote(patientId, { note_type: noteType, content, author_id: authorId })
      }
      setContent(''); setSubject(''); setObjective(''); setAssessment(''); setPlan('')
      await reload()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to save note')
    } finally {
      setBusy(false)
    }
  }

  return (
    <PanelShell
      title="Notes"
      error={error}
      addForm={
        <form onSubmit={submit} className="stack">
          <div className="grid">
            <select value={noteType} onChange={(e) => setNoteType(e.target.value)}>
              {['SOAP', 'PROGRESS', 'DISCHARGE', 'ADMISSION', 'CONSULT', 'NURSING', 'OPNOTE', 'AI_DRAFT'].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <label>
              Filter by type
              <select value={filter ?? ''} onChange={(e) => setFilter(e.target.value || undefined)}>
                <option value="">All</option>
                {['SOAP', 'PROGRESS', 'DISCHARGE', 'ADMISSION', 'CONSULT', 'NURSING', 'OPNOTE', 'AI_DRAFT'].map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
          </div>
          {noteType === 'SOAP' && (
            <div className="grid">
              <input placeholder="Subjective" value={subject} onChange={(e) => setSubject(e.target.value)} />
              <input placeholder="Objective" value={objective} onChange={(e) => setObjective(e.target.value)} />
              <input placeholder="Assessment" value={assessment} onChange={(e) => setAssessment(e.target.value)} />
              <input placeholder="Plan" value={plan} onChange={(e) => setPlan(e.target.value)} />
            </div>
          )}
          <textarea placeholder="Content" value={content} onChange={(e) => setContent(e.target.value)} rows={2} />
          {formError && <p className="alert-error">{formError}</p>}
          <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save note'}</button>
        </form>
      }
    >
      <table>
        <thead>
          <tr><th>Type</th><th>Content</th><th>Status</th><th>Created</th></tr>
        </thead>
        <tbody>
          {(data?.items ?? []).map((n: ClinicalNote) => (
            <tr key={n.id}>
              <td>{n.note_type}</td>
              <td className="clamp">{n.content}</td>
              <td>{n.approval_status}</td>
              <td>{fmt(n.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelShell>
  )
}

// ------------------------------------------------------------------ Encounters

export function EncountersPanel({ patientId }: { patientId: string }) {
  const [encounterType, setEncounterType] = useState('OUTPATIENT')
  const [reason, setReason] = useState('')
  const { data, error, reload } = useLoad(() => ehrApi.listEncounters(patientId))
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const enc = await ehrApi.createEncounter(patientId, { encounter_type: encounterType, reason: reason || undefined })
      setReason('')
      window.alert(`Encounter created: ${enc.id}`)
      await reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <PanelShell
      title="Encounters (open one to get its UUID for diagnoses)"
      error={error}
      addForm={
        <form onSubmit={submit} className="grid">
          <select value={encounterType} onChange={(e) => setEncounterType(e.target.value)}>
            {['OUTPATIENT', 'INPATIENT', 'ED', 'SURGERY', 'TELEHEALTH', 'HOME'].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input placeholder="Reason for visit" value={reason} onChange={(e) => setReason(e.target.value)} />
          <button type="submit" disabled={busy}>Open encounter</button>
        </form>
      }
    >
      <table>
        <thead>
          <tr><th>ID</th><th>Type</th><th>Reason</th><th>Status</th><th>Start</th></tr>
        </thead>
        <tbody>
          {(data?.items ?? []).map((enc: Encounter) => (
            <tr key={enc.id}>
              <td className="id-cell">{enc.id}</td>
              <td>{enc.encounter_type}</td>
              <td>{enc.reason ?? '—'}</td>
              <td>{enc.status}</td>
              <td>{fmt(enc.start_time)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelShell>
  )
}

// ------------------------------------------------------------------ Vitals

export function VitalsPanel({ patientId }: { patientId: string }) {
  const [vitalType, setVitalType] = useState('HR')
  const [num, setNum] = useState('')
  const [text, setText] = useState('')
  const [unit, setUnit] = useState('')
  const { data, error, reload } = useLoad(() => ehrApi.listVitals(patientId))
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await ehrApi.recordVitals(patientId, [{
        vital_type: vitalType,
        value_numeric: num === '' ? undefined : Number(num),
        value_text: text || undefined,
        unit: unit || undefined,
      }])
      setNum(''); setText(''); setUnit('')
      await reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <PanelShell
      title="Vitals"
      error={error}
      addForm={
        <form onSubmit={submit} className="grid">
          <select value={vitalType} onChange={(e) => setVitalType(e.target.value)}>
            {['BP', 'HR', 'RR', 'TEMP', 'SPO2', 'WEIGHT', 'HEIGHT', 'BMI', 'GLUCOSE', 'PAIN', 'GCS'].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input placeholder="Value (numeric)" type="number" step="any" value={num} onChange={(e) => setNum(e.target.value)} />
          <input placeholder="Value (text, e.g. 120/80)" value={text} onChange={(e) => setText(e.target.value)} />
          <input placeholder="Unit" value={unit} onChange={(e) => setUnit(e.target.value)} />
          <button type="submit" disabled={busy}>Record</button>
        </form>
      }
    >
      <table>
        <thead>
          <tr><th>Type</th><th>Value</th><th>Unit</th><th>Recorded</th></tr>
        </thead>
        <tbody>
          {(data?.items ?? []).map((v: Vital) => (
            <tr key={v.id}>
              <td>{v.vital_type}</td>
              <td>{v.value_numeric ?? v.value_text ?? '—'}</td>
              <td>{v.unit ?? '—'}</td>
              <td>{fmt(v.recorded_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelShell>
  )
}

// ------------------------------------------------------------------ Diagnoses

export function DiagnosesPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const [code, setCode] = useState('')
  const [desc, setDesc] = useState('')
  const [type, setType] = useState('WORKING')
  const [encounterId, setEncounterId] = useState('')
  const { data, error, reload } = useLoad(() => ehrApi.listDiagnoses(patientId))
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await ehrApi.addDiagnosis(patientId, {
        diagnosis_code: code, description: desc, type, diagnosed_by: authorId,
        encounter_id: encounterId,
      })
      setCode(''); setDesc('')
      await reload()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <PanelShell
      title="Diagnoses"
      error={error}
      addForm={
        <form onSubmit={submit} className="grid">
          <input placeholder="Encounter UUID *" value={encounterId} onChange={(e) => setEncounterId(e.target.value)} required />
          <input placeholder="ICD-10 code (e.g. J06.9)" value={code} onChange={(e) => setCode(e.target.value)} required />
          <input placeholder="Description" value={desc} onChange={(e) => setDesc(e.target.value)} required />
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {['WORKING', 'PROVISIONAL', 'FINAL', 'ADMISSION', 'DISCHARGE'].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <button type="submit" disabled={busy}>Add</button>
        </form>
      }
    >
      <p className="muted">Diagnoses are encounter-scoped: paste the encounter UUID from the Encounters tab.</p>
      <table>
        <thead>
          <tr><th>Code</th><th>Description</th><th>Type</th><th>Status</th><th /></tr>
        </thead>
        <tbody>
          {(data?.items ?? []).map((d: Diagnosis) => (
            <tr key={d.id}>
              <td>{d.diagnosis_code}</td>
              <td>{d.description}</td>
              <td>{d.type}</td>
              <td>{d.status}</td>
              <td>
                {d.status !== 'RESOLVED' && (
                  <button className="link" onClick={() => void ehrApi.resolveDiagnosis(patientId, d.id).then(reload)}>
                    resolve
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelShell>
  )
}

// ------------------------------------------------------------------ Medications

const ROUTES = ['ORAL', 'IV', 'IM', 'SC', 'TOPICAL', 'INHALED', 'RECTAL', 'SUBLINGUAL', 'OTIC', 'OPHTHALMIC', 'NASAL', 'OTHER']
const DOSE_UNITS = ['mg', 'g', 'mcg', 'mL', 'IU', 'units', 'drops', 'puffs']

function sigText(m: Medication): string {
  const parts: string[] = []
  if (m.dose != null) parts.push(`${m.dose}${m.dose_unit ? ` ${m.dose_unit}` : ''}`)
  parts.push(m.route)
  if (m.frequency) parts.push(m.frequency)
  if (m.duration) parts.push(`for ${m.duration}`)
  if (m.prn) parts.push('PRN')
  return parts.join(' · ')
}

export function MedicationsPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const [name, setName] = useState('')
  const [strength, setStrength] = useState('')
  const [dose, setDose] = useState('')
  const [doseUnit, setDoseUnit] = useState('mg')
  const [route, setRoute] = useState('ORAL')
  const [freq, setFreq] = useState('')
  const [duration, setDuration] = useState('')
  const [prn, setPrn] = useState(false)
  const [indication, setIndication] = useState('')
  const [instructions, setInstructions] = useState('')
  const [showAll, setShowAll] = useState(false)
  const { data, error, reload } = useLoad(() => ehrApi.listMedications(patientId))
  const { data: allergyData } = useLoad(() => ehrApi.listAllergies(patientId))
  const [busy, setBusy] = useState(false)

  const drugAllergies = (allergyData?.items ?? []).filter(
    (a) => a.allergen_type === 'DRUG' && a.status === 'ACTIVE',
  )
  const conflicts =
    name.trim().length > 1
      ? drugAllergies.filter((a) => {
          const al = a.allergen.toLowerCase()
          const ml = name.trim().toLowerCase()
          return al.includes(ml) || ml.includes(al)
        })
      : []

  const items = (data?.items ?? []).filter((m) => (showAll ? true : m.status === 'ACTIVE'))
  const activeCount = (data?.items ?? []).filter((m) => m.status === 'ACTIVE').length

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (
      conflicts.length > 0 &&
      !window.confirm(
        `ALLERGY ALERT\n\nThis patient has an active drug allergy:\n${conflicts
          .map((c) => `- ${c.allergen} (${c.severity}): ${c.reaction ?? 'reaction not documented'}`)
          .join('\n')}\n\nPrescribe "${name}" anyway?`,
      )
    ) {
      return
    }
    setBusy(true)
    try {
      await ehrApi.addMedication(patientId, {
        medication_name: name,
        strength: strength || undefined,
        dose: dose === '' ? undefined : Number(dose),
        dose_unit: doseUnit || undefined,
        route,
        frequency: freq || undefined,
        duration: duration || undefined,
        prn,
        indication: indication || undefined,
        instructions: instructions || undefined,
        prescriber_id: authorId,
      })
      setName(''); setStrength(''); setDose(''); setFreq(''); setDuration(''); setPrn(false); setIndication(''); setInstructions('')
      await reload()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <PanelShell
      title={`Medications (${activeCount} active)`}
      error={error}
      addForm={
        <form onSubmit={submit}>
          {conflicts.length > 0 && (
            <div className="allergy-warning">
              <strong>Allergy conflict:</strong>{' '}
              {conflicts.map((c) => `${c.allergen} (${c.severity})`).join(', ')} — confirm before prescribing.
            </div>
          )}
          <div className="grid">
            <label>
              Medication *
              <input placeholder="e.g. Amoxicillin" value={name} onChange={(e) => setName(e.target.value)} required />
            </label>
            <label>
              Strength
              <input placeholder="e.g. 500 mg" value={strength} onChange={(e) => setStrength(e.target.value)} />
            </label>
            <label>
              Dose
              <input placeholder="e.g. 1" type="number" step="any" min="0" value={dose} onChange={(e) => setDose(e.target.value)} />
            </label>
            <label>
              Dose unit
              <select value={doseUnit} onChange={(e) => setDoseUnit(e.target.value)}>
                {DOSE_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </label>
            <label>
              Route
              <select value={route} onChange={(e) => setRoute(e.target.value)}>
                {ROUTES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
            <label>
              Frequency
              <input placeholder="e.g. TID / q8h" value={freq} onChange={(e) => setFreq(e.target.value)} />
            </label>
            <label>
              Duration
              <input placeholder="e.g. 7 days" value={duration} onChange={(e) => setDuration(e.target.value)} />
            </label>
            <label className="check">
              <input type="checkbox" checked={prn} onChange={(e) => setPrn(e.target.checked)} />
              PRN (as needed)
            </label>
          </div>
          <div className="grid">
            <label>
              Indication
              <input placeholder="Why is this being prescribed?" value={indication} onChange={(e) => setIndication(e.target.value)} />
            </label>
            <label>
              Instructions to patient
              <input placeholder="e.g. Take with food" value={instructions} onChange={(e) => setInstructions(e.target.value)} />
            </label>
          </div>
          <button type="submit" disabled={busy}>{busy ? 'Prescribing…' : 'Prescribe'}</button>
        </form>
      }
    >
      <div className="filter-row">
        <button className={showAll ? 'chip' : 'chip active'} onClick={() => setShowAll(false)}>Active</button>
        <button className={showAll ? 'chip active' : 'chip'} onClick={() => setShowAll(true)}>All</button>
      </div>
      <table>
        <thead>
          <tr><th>Medication</th><th>Sig</th><th>Indication</th><th>Instructions</th><th>Prescribed</th><th>Status</th><th /></tr>
        </thead>
        <tbody>
          {items.map((m: Medication) => (
            <tr key={m.id} className={m.status !== 'ACTIVE' ? 'row-inactive' : undefined}>
              <td>
                <div className="cell-main">{m.medication_name}</div>
                <div className="muted">{m.strength ?? ''}</div>
              </td>
              <td>{sigText(m)}</td>
              <td>{m.indication ?? '—'}</td>
              <td className="clamp" title={m.instructions}>{m.instructions ?? '—'}</td>
              <td>{fmt(m.prescribed_at)}</td>
              <td><span className={`status-badge status-${m.status.toLowerCase()}`}>{m.status}</span></td>
              <td>
                {m.status === 'ACTIVE' && (
                  <button className="link danger" onClick={() => {
                    if (window.confirm(`Discontinue ${m.medication_name}?`)) {
                      void ehrApi.discontinueMedication(patientId, m.id).then(reload)
                    }
                  }}>
                    discontinue
                  </button>
                )}
                {m.status === 'DISCONTINUED' && m.discontinued_at && (
                  <span className="muted">at {fmt(m.discontinued_at)}</span>
                )}
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={7} className="muted">No {showAll ? '' : 'active '}medications recorded.</td></tr>
          )}
        </tbody>
      </table>
    </PanelShell>
  )
}

// ------------------------------------------------------------------ Orders

export function OrdersPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const [orderType, setOrderType] = useState('LAB')
  const [desc, setDesc] = useState('')
  const [priority, setPriority] = useState('ROUTINE')
  const { data, error, reload } = useLoad(() => ehrApi.listOrders(patientId))
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await ehrApi.addOrder(patientId, {
        order_type: orderType, description: desc, priority, requested_by: authorId,
      })
      setDesc('')
      await reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <PanelShell
      title="Orders"
      error={error}
      addForm={
        <form onSubmit={submit} className="grid">
          <select value={orderType} onChange={(e) => setOrderType(e.target.value)}>
            {['LAB', 'IMAGING', 'PROCEDURE', 'CONSULT', 'NURSING', 'DIET', 'BLOOD', 'OTHER'].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input placeholder="Order description *" value={desc} onChange={(e) => setDesc(e.target.value)} required />
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            {['ROUTINE', 'URGENT', 'STAT', 'ASAP'].map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <button type="submit" disabled={busy}>Place order</button>
        </form>
      }
    >
      <table>
        <thead>
          <tr><th>Type</th><th>Description</th><th>Priority</th><th>Status</th><th /></tr>
        </thead>
        <tbody>
          {(data?.items ?? []).map((o: ClinicalOrder) => (
            <tr key={o.id}>
              <td>{o.order_type}</td>
              <td>{o.description}</td>
              <td>{o.priority}</td>
              <td>{o.status}</td>
              <td>
                {o.status !== 'COMPLETED' && o.status !== 'CANCELLED' && (
                  <button className="link" onClick={() => void ehrApi.completeOrder(patientId, o.id).then(reload)}>
                    complete
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelShell>
  )
}

// ------------------------------------------------------------------ Allergies

function severityClass(severity: string): string {
  switch (severity) {
    case 'HIGH': return 'sev-high'
    case 'MEDIUM': return 'sev-medium'
    case 'LOW': return 'sev-low'
    default: return 'sev-unknown'
  }
}

export function AllergiesPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const [allergen, setAllergen] = useState('')
  const [allergenType, setAllergenType] = useState('DRUG')
  const [reaction, setReaction] = useState('')
  const [severity, setSeverity] = useState('UNKNOWN')
  const [onset, setOnset] = useState('')
  const [showResolved, setShowResolved] = useState(false)
  const { data, error, reload } = useLoad(() => ehrApi.listAllergies(patientId))
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const items = (data?.items ?? []).filter((a) => (showResolved ? true : a.status === 'ACTIVE'))
  const active = (data?.items ?? []).filter((a) => a.status === 'ACTIVE')
  const highSeverity = active.filter((a) => a.severity === 'HIGH')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setFormError(null)
    try {
      await ehrApi.addAllergy(patientId, {
        allergen,
        allergen_type: allergenType,
        reaction: reaction || undefined,
        severity,
        onset_date: onset || undefined,
        recorded_by: authorId,
      })
      setAllergen(''); setReaction(''); setOnset(''); setSeverity('UNKNOWN')
      await reload()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to record allergy')
    } finally {
      setBusy(false)
    }
  }

  return (
    <PanelShell
      title={`Allergies (${active.length} active)`}
      error={error}
      addForm={
        <form onSubmit={submit}>
          <div className="grid">
            <label>
              Allergen *
              <input placeholder="e.g. Penicillin" value={allergen} onChange={(e) => setAllergen(e.target.value)} required />
            </label>
            <label>
              Type
              <select value={allergenType} onChange={(e) => setAllergenType(e.target.value)}>
                {['DRUG', 'FOOD', 'ENVIRONMENT', 'OTHER'].map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label>
              Severity
              <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                {['LOW', 'MEDIUM', 'HIGH', 'UNKNOWN'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label>
              Onset date
              <input type="date" value={onset} onChange={(e) => setOnset(e.target.value)} />
            </label>
          </div>
          <div className="grid">
            <label>
              Reaction observed
              <input placeholder="e.g. Urticaria, anaphylaxis" value={reaction} onChange={(e) => setReaction(e.target.value)} />
            </label>
          </div>
          {allergenType === 'DRUG' && severity === 'HIGH' && (
            <div className="allergy-warning">
              High-severity drug allergy — this will trigger a prescribing alert in the Medications tab.
            </div>
          )}
          {formError && <p className="alert-error">{formError}</p>}
          <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Record allergy'}</button>
        </form>
      }
    >
      {highSeverity.length > 0 && (
        <div className="allergy-warning">
          <strong>High-severity allergies on file:</strong>{' '}
          {highSeverity.map((a) => `${a.allergen}${a.reaction ? ` — ${a.reaction}` : ''}`).join('; ')}
        </div>
      )}
      <div className="filter-row">
        <button className={!showResolved ? 'chip active' : 'chip'} onClick={() => setShowResolved(false)}>Active</button>
        <button className={showResolved ? 'chip active' : 'chip'} onClick={() => setShowResolved(true)}>All</button>
      </div>
      <table>
        <thead>
          <tr><th>Allergen</th><th>Type</th><th>Reaction</th><th>Severity</th><th>Onset</th><th>Recorded</th><th>Status</th><th /></tr>
        </thead>
        <tbody>
          {items.map((a: Allergy) => (
            <tr key={a.id} className={a.status !== 'ACTIVE' ? 'row-inactive' : undefined}>
              <td className="cell-main">{a.allergen}</td>
              <td>{a.allergen_type}</td>
              <td className="clamp" title={a.reaction}>{a.reaction ?? '—'}</td>
              <td><span className={`sev-badge ${severityClass(a.severity)}`}>{a.severity}</span></td>
              <td>{a.onset_date ? a.onset_date.slice(0, 10) : '—'}</td>
              <td>{fmt(a.recorded_at)}</td>
              <td><span className={`status-badge status-${a.status.toLowerCase()}`}>{a.status}</span></td>
              <td>
                {a.status === 'ACTIVE' && (
                  <button className="link" onClick={() => void ehrApi.resolveAllergy(patientId, a.id).then(reload)}>
                    resolve
                  </button>
                )}
                {a.status !== 'ACTIVE' && a.resolved_at && (
                  <span className="muted">at {fmt(a.resolved_at)}</span>
                )}
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={8} className="muted">No known {showResolved ? '' : 'active '}allergies recorded.</td></tr>
          )}
        </tbody>
      </table>
    </PanelShell>
  )
}

// ------------------------------------------------------------------ Problem list

export function ProblemsPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const [problem, setProblem] = useState('')
  const [code, setCode] = useState('')
  const [severity, setSeverity] = useState('')
  const { data, error, reload } = useLoad(() => ehrApi.listProblems(patientId))
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await ehrApi.addProblem(patientId, {
        problem, diagnosis_code: code || undefined, severity: severity || undefined, recorded_by: authorId,
      })
      setProblem(''); setCode('')
      await reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <PanelShell
      title="Problem List"
      error={error}
      addForm={
        <form onSubmit={submit} className="grid">
          <input placeholder="Problem *" value={problem} onChange={(e) => setProblem(e.target.value)} required />
          <input placeholder="ICD-10 code" value={code} onChange={(e) => setCode(e.target.value)} />
          <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">Severity</option>
            {['LOW', 'MEDIUM', 'HIGH'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button type="submit" disabled={busy}>Add</button>
        </form>
      }
    >
      <table>
        <thead>
          <tr><th>Problem</th><th>Code</th><th>Severity</th><th>Status</th><th /></tr>
        </thead>
        <tbody>
          {(data?.items ?? []).map((p: Problem) => (
            <tr key={p.id}>
              <td>{p.problem}</td>
              <td>{p.diagnosis_code ?? '—'}</td>
              <td>{p.severity ?? '—'}</td>
              <td>{p.status}</td>
              <td>
                {p.status !== 'RESOLVED' && (
                  <button className="link" onClick={() => void ehrApi.resolveProblem(patientId, p.id).then(reload)}>
                    resolve
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelShell>
  )
}

// ------------------------------------------------------------------ Medical history

export function MedicalHistoryPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const [historyType, setHistoryType] = useState('PAST_MEDICAL')
  const [desc, setDesc] = useState('')
  const [facility, setFacility] = useState('')
  const { data, error, reload } = useLoad(() => ehrApi.listMedicalHistory(patientId))
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await ehrApi.addMedicalHistory(patientId, {
        history_type: historyType, description: desc, facility: facility || undefined, recorded_by: authorId,
      })
      setDesc(''); setFacility('')
      await reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <PanelShell
      title="Medical History"
      error={error}
      addForm={
        <form onSubmit={submit} className="grid">
          <select value={historyType} onChange={(e) => setHistoryType(e.target.value)}>
            {['PAST_MEDICAL', 'SURGICAL', 'FAMILY', 'SOCIAL', 'MEDICATION', 'ALLERGY', 'OBSTETRIC', 'IMMUNIZATION', 'OTHER'].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input placeholder="Description *" value={desc} onChange={(e) => setDesc(e.target.value)} required />
          <input placeholder="Facility" value={facility} onChange={(e) => setFacility(e.target.value)} />
          <button type="submit" disabled={busy}>Record</button>
        </form>
      }
    >
      <table>
        <thead>
          <tr><th>Type</th><th>Description</th><th>Facility</th><th>Status</th></tr>
        </thead>
        <tbody>
          {(data?.items ?? []).map((h: MedicalHistoryEntry) => (
            <tr key={h.id}>
              <td>{h.history_type}</td>
              <td>{h.description}</td>
              <td>{h.facility ?? '—'}</td>
              <td>{h.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelShell>
  )
}

// ------------------------------------------------------------------ Timeline

export function TimelinePanel({ patientId }: { patientId: string }) {
  const { data, error } = useLoad(() => ehrApi.timeline(patientId))
  return (
    <PanelShell title="Clinical Timeline" error={error}>
      <ul className="timeline">
        {(data?.items ?? []).map((t) => (
          <li key={t.id}>
            <span className="muted">{fmt(t.occurred_at)}</span>{' '}
            <strong>{t.event_type}</strong>{' '}
            <span className="muted">({t.source})</span>
          </li>
        ))}
      </ul>
    </PanelShell>
  )
}

// ------------------------------------------------------------------ Chart

export function ChartOverview({
  patientId,
  onNavigate,
}: {
  patientId: string
  onNavigate: (tab: string) => void
}) {
  const { data, error } = useLoad(() => ehrApi.chart(patientId))
  const vitals = (data?.sections?.vitals?.items ?? []) as Array<Record<string, unknown>>
  const latestVitals = vitals.slice(0, 6)
  return (
    <PanelShell title="Patient Chart" error={error}>
      {data && (
        <>
          <div className="chart-grid">
            {Object.entries(data.sections).map(([name, section]) => (
              <button key={name} className="chart-tile" onClick={() => onNavigate(name)}>
                <strong>{section.count}</strong>
                <span>{name.replace(/_/g, ' ')}</span>
              </button>
            ))}
          </div>
          {latestVitals.length > 0 && (
            <>
              <h4 className="latest-title">Latest vitals</h4>
              <div className="latest-vitals">
                {latestVitals.map((v) => (
                  <div key={String(v.id)} className="vital-chip">
                    <strong>{v.vital_type as string}</strong>
                    <span>
                      {v.value_numeric !== undefined && v.value_numeric !== null
                        ? `${v.value_numeric}`
                        : (v.value_text as string) ?? '—'}
                      {v.unit ? ` ${v.unit}` : ''}
                    </span>
                    <em className="muted">{fmt(String(v.recorded_at ?? ''))}</em>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </PanelShell>
  )
}