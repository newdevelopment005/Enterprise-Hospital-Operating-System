// Typed client for the ehr-service REST API (envelope-aware).

import type {
  Allergy,
  AllergyIn,
  ApiEnvelope,
  ClinicalNote,
  ClinicalOrder,
  Diagnosis,
  DiagnosisIn,
  Encounter,
  MedicalHistoryEntry,
  MedicalHistoryIn,
  Medication,
  MedicationIn,
  NoteIn,
  OrderIn,
  PatientChart,
  Problem,
  ProblemIn,
  SoapNoteIn,
  TimelineEntry,
  Vital,
  VitalIn,
} from './types'

const BASE = '/api/v1/ehr/patients'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const envelope = (await response.json()) as ApiEnvelope<T>
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}

export const ehrApi = {
  // encounters
  createEncounter(patientId: string, payload: Partial<Encounter>): Promise<Encounter> {
    return request(`/${patientId}/encounters`, { method: 'POST', body: JSON.stringify(payload) })
  },
  listEncounters(patientId: string): Promise<{ items: Encounter[]; total: number }> {
    return request(`/${patientId}/encounters`)
  },

  // notes
  createSoap(patientId: string, payload: SoapNoteIn): Promise<ClinicalNote> {
    return request(`/${patientId}/soap`, { method: 'POST', body: JSON.stringify(payload) })
  },
  createProgress(patientId: string, payload: { content: string; author_id: string }): Promise<ClinicalNote> {
    return request(`/${patientId}/progress-notes`, { method: 'POST', body: JSON.stringify(payload) })
  },
  createDischarge(
    patientId: string,
    payload: { summary: string; discharge_diagnosis?: string; author_id: string },
  ): Promise<ClinicalNote> {
    return request(`/${patientId}/discharge-summary`, { method: 'POST', body: JSON.stringify(payload) })
  },
  createNote(patientId: string, payload: NoteIn): Promise<ClinicalNote> {
    return request(`/${patientId}/notes`, { method: 'POST', body: JSON.stringify(payload) })
  },
  listNotes(patientId: string, noteType?: string): Promise<{ items: ClinicalNote[]; total: number }> {
    const params = noteType ? `?note_type=${encodeURIComponent(noteType)}` : ''
    return request(`/${patientId}/notes${params}`)
  },

  // vitals
  recordVitals(patientId: string, readings: VitalIn[]): Promise<{ items: Vital[]; count: number }> {
    const body = readings.length === 1 ? readings[0] : { readings }
    return request(`/${patientId}/vitals`, { method: 'POST', body: JSON.stringify(body) })
  },
  listVitals(patientId: string): Promise<{ items: Vital[]; total: number }> {
    return request(`/${patientId}/vitals`)
  },

  // diagnoses
  addDiagnosis(patientId: string, payload: DiagnosisIn): Promise<Diagnosis> {
    return request(`/${patientId}/diagnoses`, { method: 'POST', body: JSON.stringify(payload) })
  },
  listDiagnoses(patientId: string): Promise<{ items: Diagnosis[]; total: number }> {
    return request(`/${patientId}/diagnoses`)
  },
  resolveDiagnosis(patientId: string, diagnosisId: string): Promise<Diagnosis> {
    return request(`/${patientId}/diagnoses/${diagnosisId}/resolve`, { method: 'POST', body: '{}' })
  },

  // medications
  addMedication(patientId: string, payload: MedicationIn): Promise<Medication> {
    return request(`/${patientId}/medications`, { method: 'POST', body: JSON.stringify(payload) })
  },
  listMedications(patientId: string): Promise<{ items: Medication[]; total: number }> {
    return request(`/${patientId}/medications`)
  },
  discontinueMedication(patientId: string, medicationId: string): Promise<Medication> {
    return request(`/${patientId}/medications/${medicationId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'DISCONTINUED' }),
    })
  },

  // orders
  addOrder(patientId: string, payload: OrderIn): Promise<ClinicalOrder> {
    return request(`/${patientId}/orders`, { method: 'POST', body: JSON.stringify(payload) })
  },
  listOrders(patientId: string): Promise<{ items: ClinicalOrder[]; total: number }> {
    return request(`/${patientId}/orders`)
  },
  completeOrder(
    patientId: string,
    orderId: string,
    resultSummary?: string,
  ): Promise<ClinicalOrder> {
    return request(`/${patientId}/orders/${orderId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'COMPLETED', result_summary: resultSummary }),
    })
  },

  // allergies
  addAllergy(patientId: string, payload: AllergyIn): Promise<Allergy> {
    return request(`/${patientId}/allergies`, { method: 'POST', body: JSON.stringify(payload) })
  },
  listAllergies(patientId: string): Promise<{ items: Allergy[]; total: number }> {
    return request(`/${patientId}/allergies`)
  },
  resolveAllergy(patientId: string, allergyId: string): Promise<Allergy> {
    return request(`/${patientId}/allergies/${allergyId}/resolve`, { method: 'POST', body: '{}' })
  },

  // problem list
  addProblem(patientId: string, payload: ProblemIn): Promise<Problem> {
    return request(`/${patientId}/problems`, { method: 'POST', body: JSON.stringify(payload) })
  },
  listProblems(patientId: string): Promise<{ items: Problem[]; total: number }> {
    return request(`/${patientId}/problems`)
  },
  resolveProblem(patientId: string, problemId: string): Promise<Problem> {
    return request(`/${patientId}/problems/${problemId}/resolve`, { method: 'POST', body: '{}' })
  },

  // medical history
  addMedicalHistory(patientId: string, payload: MedicalHistoryIn): Promise<MedicalHistoryEntry> {
    return request(`/${patientId}/medical-history`, { method: 'POST', body: JSON.stringify(payload) })
  },
  listMedicalHistory(patientId: string): Promise<{ items: MedicalHistoryEntry[]; total: number }> {
    return request(`/${patientId}/medical-history`)
  },

  // timeline & chart
  timeline(patientId: string): Promise<{ items: TimelineEntry[]; total: number }> {
    return request(`/${patientId}/timeline`)
  },
  chart(patientId: string): Promise<PatientChart> {
    return request(`/${patientId}/chart`)
  },
}