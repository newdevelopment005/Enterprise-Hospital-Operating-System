import { useState } from 'react'
import {
  AllergiesPanel,
  ChartOverview,
  DEFAULT_AUTHOR,
  DiagnosesPanel,
  EncountersPanel,
  MedicalHistoryPanel,
  MedicationsPanel,
  NotesPanel,
  OrdersPanel,
  ProblemsPanel,
  TimelinePanel,
  VitalsPanel,
} from './components/Panels'

type Tab = 'chart' | 'encounters' | 'notes' | 'vitals' | 'diagnoses' | 'medications' | 'orders'
  | 'allergies' | 'problems' | 'history' | 'timeline'

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'chart', label: 'Chart' },
  { key: 'encounters', label: 'Encounters' },
  { key: 'notes', label: 'Notes' },
  { key: 'vitals', label: 'Vitals' },
  { key: 'diagnoses', label: 'Diagnoses' },
  { key: 'medications', label: 'Medications' },
  { key: 'orders', label: 'Orders' },
  { key: 'allergies', label: 'Allergies' },
  { key: 'problems', label: 'Problems' },
  { key: 'history', label: 'Medical History' },
  { key: 'timeline', label: 'Timeline' },
]

const SECTION_TAB: Record<string, Tab> = {
  encounters: 'encounters',
  notes: 'notes',
  vitals: 'vitals',
  diagnoses: 'diagnoses',
  medications: 'medications',
  orders: 'orders',
  allergies: 'allergies',
  problems: 'problems',
  medical_history: 'history',
}

export default function App() {
  const [patientId, setPatientId] = useState('')
  const [active, setActive] = useState<string>('')
  const [authorId, setAuthorId] = useState(DEFAULT_AUTHOR)

  const ready = /^[0-9a-fA-F-]{36}$/.test(patientId)

  return (
    <main className="container">
      <header>
        <h1>EHOS · Clinical EHR</h1>
        <form className="patient-row" onSubmit={(e) => e.preventDefault()}>
          <input
            placeholder="Patient UUID (from patient-service)"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value.trim())}
          />
          <input
            placeholder="Clinician UUID (author)"
            value={authorId}
            onChange={(e) => setAuthorId(e.target.value.trim())}
          />
        </form>
      </header>

      {!ready && <p className="muted">Enter a patient UUID to open the chart.</p>}

      {ready && (
        <>
          <nav className="tabs">
            {TABS.map((t) => (
              <button
                key={t.key}
                className={active === t.key ? 'active' : ''}
                onClick={() => setActive(t.key)}
              >
                {t.label}
              </button>
            ))}
          </nav>

          {active === 'chart' && (
            <ChartOverview patientId={patientId} onNavigate={(name) => setActive(SECTION_TAB[name] ?? 'chart')} />
          )}
          {active === 'encounters' && <EncountersPanel patientId={patientId} />}
          {active === 'notes' && <NotesPanel patientId={patientId} authorId={authorId} />}
          {active === 'vitals' && <VitalsPanel patientId={patientId} />}
          {active === 'diagnoses' && <DiagnosesPanel patientId={patientId} authorId={authorId} />}
          {active === 'medications' && <MedicationsPanel patientId={patientId} authorId={authorId} />}
          {active === 'orders' && <OrdersPanel patientId={patientId} authorId={authorId} />}
          {active === 'allergies' && <AllergiesPanel patientId={patientId} authorId={authorId} />}
          {active === 'problems' && <ProblemsPanel patientId={patientId} authorId={authorId} />}
          {active === 'history' && <MedicalHistoryPanel patientId={patientId} authorId={authorId} />}
          {active === 'timeline' && <TimelinePanel patientId={patientId} />}
        </>
      )}
    </main>
  )
}