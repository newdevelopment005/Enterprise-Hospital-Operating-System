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
import { AppointmentsPanel } from './components/AppointmentsPanel'
import { BillingPanel } from './components/BillingPanel'
import { LaboratoryPanel } from './components/LaboratoryPanel'
import { PharmacyPanel } from './components/PharmacyPanel'
import { PrescriptionsPanel } from './components/PrescriptionsPanel'
import { QueuesPanel } from './components/QueuesPanel'
import { RadiologyPanel } from './components/RadiologyPanel'
import { InventoryPanel } from './components/InventoryPanel'
import { WorkflowPanel } from './components/WorkflowPanel'
import { DocumentationPanel } from './components/DocumentationPanel'
import { InsurancePanel } from './components/InsurancePanel'
import { ReportingPanel } from './components/ReportingPanel'
import { PatientBanner } from './components/PatientBanner'
import { InfoPanel } from './components/PatientInfo'
import { PatientSearch } from './components/PatientSearch'
import type { PatientSummary } from './lib/types'

type Tab = 'info' | 'chart' | 'appointments' | 'queues' | 'billing' | 'prescriptions' | 'pharmacy' | 'laboratory' | 'radiology' | 'inventory'
  | 'workflow' | 'documentation' | 'insurance' | 'reporting' | 'encounters'
  | 'notes' | 'vitals' | 'diagnoses' | 'medications' | 'orders' | 'allergies' | 'problems' | 'history' | 'timeline'

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'info', label: 'Info' },
  { key: 'chart', label: 'Chart' },
  { key: 'appointments', label: 'Appointments' },
  { key: 'queues', label: 'Queues' },
  { key: 'billing', label: 'Billing' },
  { key: 'prescriptions', label: 'Prescriptions' },
  { key: 'pharmacy', label: 'Pharmacy' },
  { key: 'laboratory', label: 'Laboratory' },
  { key: 'radiology', label: 'Radiology' },
  { key: 'inventory', label: 'Inventory' },
  { key: 'workflow', label: 'Workflows' },
  { key: 'documentation', label: 'Documentation' },
  { key: 'insurance', label: 'Insurance' },
  { key: 'reporting', label: 'Reporting' },
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
  const [active, setActive] = useState<Tab>('info')
  const [authorId, setAuthorId] = useState(DEFAULT_AUTHOR)

  const ready = /^[0-9a-fA-F-]{36}$/.test(patientId)

  const openPatient = (p: PatientSummary) => {
    setPatientId(p.id)
    setActive('chart')
  }

  return (
    <main className="container">
      <header>
        <h1>EHOS · Clinical EHR</h1>
        <div className="patient-row">
          <PatientSearch onSelected={openPatient} />
          <input
            placeholder="Or paste patient UUID"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value.trim())}
          />
          <input
            placeholder="Clinician UUID (author)"
            value={authorId}
            onChange={(e) => setAuthorId(e.target.value.trim())}
          />
        </div>
      </header>

      {!ready && <p className="muted">Search for a patient or paste a patient UUID to open the chart.</p>}

      {ready && (
        <>
          <PatientBanner patientId={patientId} />

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

          {active === 'info' && <InfoPanel patientId={patientId} />}
          {active === 'chart' && (
            <ChartOverview
              patientId={patientId}
              onNavigate={(name) => setActive(SECTION_TAB[name] ?? 'info')}
            />
          )}
          {active === 'appointments' && <AppointmentsPanel patientId={patientId} />}
          {active === 'queues' && <QueuesPanel patientId={patientId} />}
          {active === 'billing' && <BillingPanel patientId={patientId} />}
          {active === 'prescriptions' && <PrescriptionsPanel patientId={patientId} authorId={authorId} />}
          {active === 'pharmacy' && <PharmacyPanel patientId={patientId} authorId={authorId} />}
          {active === 'laboratory' && <LaboratoryPanel patientId={patientId} authorId={authorId} />}
          {active === 'radiology' && <RadiologyPanel patientId={patientId} authorId={authorId} />}
          {active === 'inventory' && <InventoryPanel patientId={patientId} authorId={authorId} />}
          {active === 'workflow' && <WorkflowPanel patientId={patientId} authorId={authorId} />}
          {active === 'documentation' && <DocumentationPanel patientId={patientId} authorId={authorId} />}
          {active === 'insurance' && <InsurancePanel patientId={patientId} authorId={authorId} />}
          {active === 'reporting' && <ReportingPanel patientId={patientId} authorId={authorId} />}
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