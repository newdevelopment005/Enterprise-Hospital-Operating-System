// Shared types for the EHOS patient-service REST API (snake_case to match the
// FastAPI/pydantic DTOs).

export interface EmergencyContact {
  name: string
  relationship: string
  phone: string
  alternate_phone?: string
}

export interface Address {
  address_type: 'HOME' | 'WORK' | 'BILLING' | 'CONTACT'
  line1?: string
  line2?: string
  city?: string
  state_province?: string
  postal_code?: string
  country?: string
  is_primary?: boolean
}

export interface Identifier {
  identifier_type: 'NATIONAL_ID' | 'PASSPORT' | 'INSURANCE' | 'HOSPITAL'
  identifier_value: string
  issuer?: string
  valid_from?: string
  valid_to?: string
  is_primary?: boolean
}

export interface Insurance {
  provider_name: string
  provider_code?: string
  card_number?: string
  policy_number?: string
  member_number?: string
  relation_to_subscriber?: 'SELF' | 'SPOUSE' | 'DEPENDENT' | 'OTHER'
  coverage_type?: 'INPATIENT' | 'OUTPATIENT' | 'DENTAL' | 'OPTICAL' | 'MATERNITY' | 'SURGERY' | 'COMBO'
  valid_from?: string
  valid_to?: string
  remarks?: string
}

export interface MedicalAlert {
  alert_type:
    | 'ALLERGY'
    | 'CONDITION'
    | 'FALL_RISK'
    | 'LATE_CREATION'
    | 'DRUG_SENSITIVITY'
    | 'INFECTION'
    | 'OTHER'
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  title: string
  description?: string
}

export interface Consent {
  consent_type: 'TREATMENT' | 'DATA_SHARING' | 'RESEARCH' | 'TELEHEALTH' | 'AUTOMATION'
  granted: boolean
  expiry_date?: string
  documentation_ref?: string
}

export interface RegisterPatient {
  first_name: string
  last_name: string
  other_names?: string
  date_of_birth?: string
  gender?: 'MALE' | 'FEMALE' | 'OTHER' | 'UNDISCLOSED'
  blood_group?: string
  nationality?: string
  marital_status?: string
  language_pref?: string
  national_identifier?: string
  identifiers?: Identifier[]
  contacts?: EmergencyContact[]
  addresses?: Address[]
  emergency_contact?: EmergencyContact
  insurance?: Insurance
  alerts?: MedicalAlert[]
  consents?: Consent[]
}

export interface PatientSummary {
  id: string
  patient_number?: string
  mrn?: string
  first_name: string
  last_name: string
  other_names?: string
  date_of_birth?: string
  gender?: string
  nationality?: string
  biometrics_ready: boolean
  merged_into_id?: string
  created_at: string
}

export interface PatientDetail extends PatientSummary {
  blood_group?: string
  marital_status?: string
  language_pref?: string
  contact_info?: Record<string, unknown> | null
  address?: Record<string, unknown> | null
  emergency_contact?: EmergencyContact
  registration_date: string
  consent_summary?: Record<string, unknown> | null
  deceased_at?: string
}

export interface TimelineEntry {
  id: string
  event_type: string
  source: string
  occurred_at: string
  actor?: string
  details?: Record<string, unknown> | null
}

export interface SearchResult {
  patients: PatientSummary[]
  total: number
  limit: number
  offset: number
}

export interface ApiEnvelope<T> {
  success: boolean
  data: T
  errorCode?: string
  message?: string
}