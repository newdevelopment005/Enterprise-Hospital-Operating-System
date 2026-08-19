// Shared types for the ehr-service REST API (snake_case to match DTOs).

export interface Encounter {
  id: string
  patient_id: string
  encounter_type: string
  visit_number?: string
  provider_id?: string
  start_time: string
  end_time?: string
  reason?: string
  status: string
}

export interface SoapNoteIn {
  subjective?: string
  objective?: string
  assessment?: string
  plan?: string
  encounter_id?: string
  author_id: string
}

export interface NoteIn {
  note_type: string
  content: string
  content_struct?: Record<string, unknown> | null
  encounter_id?: string
  author_id: string
}

export interface ClinicalNote {
  id: string
  patient_id: string
  note_type: string
  content: string
  content_struct?: Record<string, unknown> | null
  author_id?: string
  approval_status: string
  source?: string
  created_at: string
}

export interface VitalIn {
  vital_type: string
  value_numeric?: number
  value_text?: string
  unit?: string
  recorded_at?: string
  recorded_by?: string
  encounter_id?: string
}

export interface Vital {
  id: string
  patient_id: string
  vital_type: string
  value_numeric?: number
  value_text?: string
  unit?: string
  recorded_at: string
}

export interface DiagnosisIn {
  diagnosis_code: string
  code_system?: string
  description: string
  type?: string
  encounter_id: string
  diagnosed_by: string
  present_on_admission?: boolean
}

export interface Diagnosis {
  id: string
  patient_id: string
  diagnosis_code: string
  description: string
  type: string
  status: string
  diagnosed_at: string
}

export interface MedicationIn {
  medication_name: string
  strength?: string
  dose?: number
  dose_unit?: string
  route?: string
  frequency?: string
  prn?: boolean
  indication?: string
  instructions?: string
  prescriber_id?: string
  encounter_id?: string
}

export interface Medication {
  id: string
  patient_id: string
  medication_name: string
  strength?: string
  route: string
  frequency?: string
  prn: boolean
  indication?: string
  prescribed_at: string
  status: string
}

export interface OrderIn {
  order_type: string
  description: string
  priority?: string
  indications?: string
  requested_by?: string
  encounter_id?: string
}

export interface ClinicalOrder {
  id: string
  patient_id: string
  order_type: string
  description: string
  priority: string
  requested_at: string
  result_summary?: string
  status: string
}

export interface AllergyIn {
  allergen: string
  allergen_type: string
  reaction?: string
  severity?: string
  recorded_by?: string
  encounter_id?: string
}

export interface Allergy {
  id: string
  patient_id: string
  allergen: string
  allergen_type: string
  reaction?: string
  severity: string
  recorded_at: string
  status: string
}

export interface ProblemIn {
  problem: string
  diagnosis_code?: string
  onset_date?: string
  severity?: string
  note?: string
  recorded_by?: string
}

export interface Problem {
  id: string
  patient_id: string
  problem: string
  diagnosis_code?: string
  severity?: string
  status: string
}

export interface MedicalHistoryIn {
  history_type: string
  description: string
  occurred_date?: string
  facility?: string
  notes?: string
  recorded_by?: string
  encounter_id?: string
}

export interface MedicalHistoryEntry {
  id: string
  patient_id: string
  history_type: string
  description: string
  occurred_date?: string
  facility?: string
  created_at: string
  status: string
}

export interface TimelineEntry {
  id: string
  patient_id: string
  event_type: string
  source: string
  entity_type?: string
  occurred_at: string
  details?: Record<string, unknown> | null
}

export interface ChartSection {
  count: number
  items: Array<Record<string, unknown>>
}

export interface PatientChart {
  patient_id: string
  sections: Record<string, ChartSection>
}

export interface ApiEnvelope<T> {
  success: boolean
  data: T
  errorCode?: string
  message?: string
}