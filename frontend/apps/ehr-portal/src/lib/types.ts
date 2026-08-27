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
  duration?: string
  prn?: boolean
  start_date?: string
  end_date?: string
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
  dose?: number | null
  dose_unit?: string | null
  route: string
  frequency?: string
  duration?: string
  prn: boolean
  start_date?: string | null
  end_date?: string | null
  indication?: string
  instructions?: string
  prescribed_at: string
  discontinued_at?: string | null
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
  onset_date?: string
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
  onset_date?: string | null
  recorded_at: string
  resolved_at?: string | null
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

// ---- patient-service (MPI) ------------------------------------------------

export interface PatientSummary {
  id: string
  patient_number: string | null
  mrn: string | null
  first_name: string
  last_name: string
  other_names: string | null
  date_of_birth: string | null
  gender: string | null
  nationality: string | null
  biometrics_ready: boolean
  merged_into_id: string | null
  created_at: string
}

export interface PatientDetail extends PatientSummary {
  blood_group: string | null
  marital_status: string | null
  language_pref: string
  contact_info: Record<string, unknown> | null
  address: Record<string, unknown> | null
  emergency_contact: Record<string, unknown> | null
  registration_date: string
  consent_summary: Record<string, unknown> | null
  deceased_at: string | null
}

export interface MedicalAlert {
  id: string
  alert_type: string
  severity: string
  title: string
  description: string | null
  active: boolean
  resolved_at: string | null
  created_at: string
}

// ---- appointment-service (scheduling) --------------------------------------

export interface AppointmentIn {
  patient_id: string
  provider_id?: string
  department_id?: string
  appointment_type: string
  start_time: string
  duration_min?: number
  reason?: string
  priority?: string
  source?: string
}

export interface Appointment {
  id: string
  patient_id: string
  provider_id: string | null
  department_id: string | null
  appointment_type: string
  start_time: string
  end_time: string | null
  duration_min: number | null
  status: string
  reason: string | null
  priority: string
  source: string
  consultation_room: string | null
  cancellation_reason: string | null
  cancelled_at: string | null
  created_at: string
}

export interface AvailabilitySlot {
  start: string
  end: string
  available: boolean
}

// ---- queue-service (digital queues) -----------------------------------------

export interface Queue {
  id: string
  queue_type: string
  name: string | null
  department_id: string | null
  is_active: boolean
  created_at: string
}

export interface QueueEntry {
  id: string
  queue_id: string
  patient_id: string
  ticket_number: string
  priority: number
  status: string
  joined_at: string
  called_at?: string | null
  completed_at?: string | null
  wait_time_min?: number | null
}

export interface QueueBoard {
  queue: Queue
  now_serving: QueueEntry | null
  waiting: QueueEntry[]
  counts: Record<string, number>
}

// ---- billing-service (finance) ----------------------------------------------

export interface Charge {
  id: string
  patient_id: string
  encounter_id?: string | null
  service_date: string
  item_type: string
  item_code?: string | null
  description: string
  quantity: number
  unit_price: number
  discount: number
  status: string
  created_at?: string | null
}

export interface ChargeIn {
  patient_id: string
  item_type: string
  description: string
  quantity?: number
  unit_price: number
}

export interface Invoice {
  id: string
  invoice_number: string
  patient_id: string
  total_amount: number
  insurance_amount: number
  patient_amount: number
  paid_amount: number
  currency: string
  issued_date: string
  due_date?: string | null
  status: string
  void_reason?: string | null
  balance_due?: number
  items?: Array<{ id: string; description: string; quantity: number; unit_price: number; amount: number }>
  payments?: Array<{ id: string; amount: number; payment_method: string; status: string }>
}

export interface PatientBillingSummary {
  patient_id: string
  invoices: Invoice[]
  pending_charge_count: number
  totals: { billed: number; paid: number; outstanding: number }
}

// ---- prescription-service (prescribing) --------------------------------------

export interface RxItemIn {
  medication: string
  dosage: string
  frequency: string
  route?: string
  duration_days?: number
  instructions?: string
}

export interface PrescriptionIn {
  patient_id: string
  prescriber_id: string
  therapy_type?: string
  reason?: string
  items: RxItemIn[]
  override_flags?: boolean
}

export interface RxItem {
  id: string
  medication: string
  dosage: string
  frequency: string
  route?: string | null
  duration_days?: number | null
  instructions?: string | null
  status: string
}

export interface Prescription {
  id: string
  patient_id: string
  prescriber_id: string
  issue_date: string
  therapy_type: string | null
  allergy_checked: boolean
  interaction_checked: boolean
  reason?: string | null
  status: string
  cancellation_reason?: string | null
  audit_reference?: string | null
  items?: RxItem[]
  administrations?: Array<{
    id: string
    medication: string
    dose: string
    administered_at: string
    status: string
  }>
}

export interface PatientAllergy {
  id: string
  allergen: string
  allergen_type: string
  severity: string
  reaction?: string | null
  confirmed: boolean
  recorded_at?: string | null
}

// ---- pharmacy-service (dispensing) -------------------------------------------

export interface PharmacyMedication {
  id: string
  code: string
  name: string
  generic_name?: string | null
  strength?: string | null
  form?: string | null
  controlled: boolean
  total_stock: number
}

export interface StockBatch {
  id: string
  location: string
  batch_number: string | null
  expiry_date?: string | null
  quantity: number
}

export interface DispensingRecord {
  id: string
  patient_id: string
  prescription_id?: string | null
  medication_id: string
  quantity: number
  batch_number?: string | null
  price?: number | null
  status: string
  dispensed_at?: string | null
  returned_reason?: string | null
}

export interface ApiEnvelope<T> {
  success: boolean
  data: T
  errorCode?: string
  message?: string
}

// ---- laboratory-service ---------------------------------------------------------

export interface LabTest {
  id: string
  code: string
  name: string
  category: string
  unit?: string | null
  reference_low?: number | null
  reference_high?: number | null
  specimen_type?: string | null
  turnaround_min?: number | null
  is_active: boolean
  status: string
  created_at: string
  updated_at: string
  version: number
}

export interface LabTestCreate {
  code: string
  name: string
  category: string
  unit?: string
  reference_low?: number
  reference_high?: number
  specimen_type?: string
  turnaround_min?: number
  is_active: boolean
}

export interface LabOrderItem {
  id: string
  lab_order_id: string
  test_id?: string | null
  test_name: string
  specimen_type?: string | null
  status: string
  created_at: string
  updated_at: string
  version: number
}

export interface LabOrderItemCreate {
  test_id?: string
  test_name: string
  specimen_type?: string
}

export interface LabOrder {
  id: string
  patient_id: string
  patient_snapshot?: Record<string, unknown> | null
  encounter_id?: string | null
  ordering_doctor: string
  priority: string
  clinical_notes?: string | null
  status: string
  ordered_at: string
  created_at: string
  updated_at: string
  version: number
  items: LabOrderItem[]
}

export interface LabOrderCreate {
  patient_id: string
  encounter_id?: string
  ordering_doctor: string
  priority: 'ROUTINE' | 'URGENT' | 'STAT'
  clinical_notes?: string
  items: LabOrderItemCreate[]
}

export interface LabOrderUpdate {
  priority?: 'ROUTINE' | 'URGENT' | 'STAT'
  clinical_notes?: string
  status?: string
}

export interface Sample {
  id: string
  lab_order_id: string
  patient_id: string
  barcode: string
  sample_type: string
  collection_time?: string | null
  collected_by?: string | null
  received_at?: string | null
  received_by?: string | null
  status: string
  rejection_reason?: string | null
  created_at: string
  updated_at: string
  version: number
}

export interface SampleCreate {
  lab_order_id: string
  patient_id: string
  barcode: string
  sample_type: string
}

export interface SampleCollect {
  collected_by: string
  collection_time?: string
}

export interface SampleReceive {
  received_by: string
  received_at?: string
}

export interface SampleReject {
  rejection_reason: string
}

export interface LabResult {
  id: string
  order_item_id: string
  sample_id?: string | null
  patient_id: string
  test_id?: string | null
  test_name: string
  result_numeric?: number | null
  result_text?: string | null
  unit?: string | null
  reference_range?: string | null
  flag?: string | null
  performed_by?: string | null
  performed_at?: string | null
  verified_by?: string | null
  verified_at?: string | null
  status: string
  instrumentation?: string | null
  created_at: string
  updated_at: string
  version: number
}

export interface LabResultCreate {
  order_item_id: string
  sample_id?: string
  patient_id: string
  test_id?: string
  test_name: string
  result_numeric?: number
  result_text?: string
  unit?: string
  reference_range?: string
  flag?: 'NORMAL' | 'HIGH' | 'LOW' | 'CRITICAL' | 'ABNORMAL'
  performed_by?: string
  performed_at?: string
  verified_by?: string
  verified_at?: string
  status: 'PRELIMINARY' | 'VERIFIED' | 'AMENDED' | 'CANCELLED'
  instrumentation?: string
}

export interface LabResultUpdate {
  result_numeric?: number
  result_text?: string
  unit?: string
  reference_range?: string
  flag?: 'NORMAL' | 'HIGH' | 'LOW' | 'CRITICAL' | 'ABNORMAL'
  performed_by?: string
  performed_at?: string
  status?: 'PRELIMINARY' | 'VERIFIED' | 'AMENDED' | 'CANCELLED'
  instrumentation?: string
}

export interface LabResultVerify {
  verified_by: string
  verified_at?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// ---- radiology-service (imaging) -------------------------------------------

export interface Modality {
  id: string
  code: string
  name: string
  description?: string
  is_active: boolean
  status: string
  created_at: string
  updated_at: string
  version: number
}

export interface ModalityCreate {
  code: string
  name: string
  description?: string
  is_active?: boolean
}

export interface RadiologyOrder {
  id: string
  patient_id: string
  encounter_id?: string
  ordering_doctor: string
  modality_code: string
  body_region: string
  clinical_indication?: string
  priority: 'ROUTINE' | 'URGENT' | 'STAT'
  contrast: boolean
  ordered_at: string
  scheduled_at?: string
  status: 'ORDERED' | 'SCHEDULED' | 'PERFORMING' | 'COMPLETED' | 'CANCELLED'
  created_at: string
  updated_at: string
  version: number
}

export interface RadiologyOrderCreate {
  patient_id: string
  encounter_id?: string
  ordering_doctor: string
  modality_code: string
  body_region: string
  clinical_indication?: string
  priority?: 'ROUTINE' | 'URGENT' | 'STAT'
  contrast?: boolean
}

export interface RadiologyOrderUpdate {
  priority?: 'ROUTINE' | 'URGENT' | 'STAT'
  body_region?: string
  clinical_indication?: string
  contrast?: boolean
  status?: 'ORDERED' | 'SCHEDULED' | 'PERFORMING' | 'COMPLETED' | 'CANCELLED'
}

export interface Study {
  id: string
  order_id: string
  patient_id: string
  modality_code: string
  body_region: string
  study_instance_uid?: string
  accession_number?: string
  performed_by?: string
  performed_at?: string
  started_at?: string
  completed_at?: string
  status: 'SCHEDULED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED'
  technician_notes?: string
  created_at: string
  updated_at: string
  version: number
}

export interface StudyCreate {
  order_id: string
  patient_id: string
  modality_code: string
  body_region: string
  study_instance_uid?: string
  accession_number?: string
}

export interface RadiologyReport {
  id: string
  order_id: string
  patient_id: string
  study_id?: string
  findings?: string
  impression?: string
  recommendation?: string
  structured_report?: Record<string, unknown>
  status: 'DRAFT' | 'PRELIMINARY' | 'FINAL' | 'AMENDED' | 'CANCELLED'
  signed_by?: string
  signed_at?: string
  created_at: string
  updated_at: string
  version: number
}

export interface RadiologyReportCreate {
  order_id: string
  patient_id: string
  study_id?: string
  findings?: string
  impression?: string
  recommendation?: string
  structured_report?: Record<string, unknown>
}

export interface RadiologyReportUpdate {
  findings?: string
  impression?: string
  recommendation?: string
  structured_report?: Record<string, unknown>
  status?: 'DRAFT' | 'PRELIMINARY' | 'FINAL' | 'AMENDED' | 'CANCELLED'
}

// ---- inventory-service -------------------------------------------------------

export interface InventoryItem {
  id: string
  sku: string
  name: string
  category: string
  unit_of_measure: string
  unit_cost?: number | null
  reorder_point: number
  reorder_qty: number
  is_active: boolean
  status: string
  created_at: string
  updated_at: string
  version: number
}

export interface InventoryItemCreate {
  sku: string
  name: string
  category: string
  unit_of_measure: string
  unit_cost?: number
  reorder_point?: number
  reorder_qty?: number
  is_active?: boolean
}

export interface StockItem {
  id: string
  item_id: string
  location: string
  lot_number?: string | null
  expiry_date?: string | null
  quantity_on_hand: number
  quantity_reserved: number
  status: string
  created_at: string
  updated_at: string
  version: number
}

export interface StockItemCreate {
  item_id: string
  location: string
  lot_number?: string
  expiry_date?: string
  quantity_on_hand?: number
}

export interface StockMovement {
  id: string
  stock_item_id: string
  movement_type: 'RECEIPT' | 'DISPENSE' | 'TRANSFER' | 'ADJUSTMENT' | 'WRITE_OFF' | 'RETURN'
  quantity: number
  reference_type?: string | null
  reference_id?: string | null
  reason?: string | null
  performed_by: string
  performed_at: string
  status: string
  created_at: string
  updated_at: string
  version: number
}

export interface StockMovementCreate {
  stock_item_id: string
  movement_type: 'RECEIPT' | 'DISPENSE' | 'TRANSFER' | 'ADJUSTMENT' | 'WRITE_OFF' | 'RETURN'
  quantity: number
  reference_type?: string
  reference_id?: string
  reason?: string
  performed_by: string
}

export interface ReorderAlert {
  id: string
  item_id: string
  location: string
  quantity_on_hand: number
  reorder_point: number
  status: string
  created_at: string
  updated_at: string
}

// ---- workflow-service ---------------------------------------------------------

export interface WorkflowDefinition {
  id: string
  key: string
  name: string
  description?: string | null
  states?: Record<string, unknown> | null
  transitions?: Record<string, unknown> | null
  initial_state: string
  is_active: boolean
  version: number
  status: string
  created_at: string
  updated_at: string
  model_version: number
}

export interface WorkflowDefinitionCreate {
  key: string
  name: string
  description?: string
  states?: Record<string, unknown>
  transitions?: Record<string, unknown>
  initial_state: string
  is_active?: boolean
}

export interface WorkflowInstance {
  id: string
  definition_id: string
  entity_type: string
  entity_id: string
  patient_id?: string | null
  context?: Record<string, unknown> | null
  current_state: string
  started_at: string
  completed_at?: string | null
  status: string
  created_at: string
  updated_at: string
  model_version: number
}

export interface WorkflowInstanceCreate {
  definition_id: string
  entity_type: string
  entity_id: string
  patient_id?: string
  context?: Record<string, unknown>
}

export interface WorkflowTransition {
  id: string
  instance_id: string
  from_state: string
  to_state: string
  event: string
  actor_id: string
  comment?: string | null
  event_metadata?: Record<string, unknown> | null
  performed_at: string
  created_at: string
  status: string
  model_version: number
}

export interface WorkflowEventFire {
  event: string
  actor_id: string
  comment?: string
  metadata?: Record<string, unknown>
}

// ---- clinical-documentation-service -------------------------------------------

export interface ClinicalNoteDoc {
  id: string
  patient_id: string
  encounter_id?: string | null
  author_id: string
  note_type: string
  title?: string | null
  content?: string | null
  structured_data?: Record<string, unknown> | null
  status: string
  signed_by?: string | null
  signed_at?: string | null
  created_at: string
  updated_at: string
  model_version: number
}

export interface ClinicalNoteDocCreate {
  patient_id: string
  encounter_id?: string
  author_id: string
  note_type: string
  title?: string
  content?: string
  structured_data?: Record<string, unknown>
}

export interface DocNoteVersion {
  id: string
  note_id: string
  version_number: number
  content?: string | null
  structured_data?: Record<string, unknown> | null
  changed_by: string
  change_summary?: string | null
  created_at: string
  status: string
  model_version: number
}

export interface DocTemplate {
  id: string
  name: string
  note_type: string
  content?: string | null
  structured_schema?: Record<string, unknown> | null
  is_active: boolean
  status: string
  created_at: string
  updated_at: string
  model_version: number
}

export interface DocTemplateCreate {
  name: string
  note_type: string
  content?: string
  structured_schema?: Record<string, unknown>
  is_active?: boolean
}

// ---- insurance-service ---------------------------------------------------------

export interface Coverage {
  id: string
  patient_id: string
  payer_name: string
  plan_name?: string | null
  policy_number: string
  group_number?: string | null
  coverage_type: string
  effective_date: string
  termination_date?: string | null
  copay?: number | null
  deductible?: number | null
  coinsurance?: number | null
  is_active: boolean
  status: string
  created_at: string
  updated_at: string
  model_version: number
}

export interface CoverageCreate {
  patient_id: string
  payer_name: string
  plan_name?: string
  policy_number: string
  group_number?: string
  coverage_type: string
  effective_date: string
  termination_date?: string
  copay?: number
  deductible?: number
  coinsurance?: number
  is_active?: boolean
}

export interface Claim {
  id: string
  patient_id: string
  coverage_id: string
  encounter_id?: string | null
  service_date: string
  diagnosis_codes?: string[] | null
  procedure_codes?: string[] | null
  total_amount: number
  approved_amount?: number | null
  paid_amount?: number | null
  patient_responsibility?: number | null
  status: string
  denial_reason?: string | null
  submitted_at?: string | null
  adjudicated_at?: string | null
  created_at: string
  updated_at: string
  model_version: number
}

export interface ClaimCreate {
  patient_id: string
  coverage_id: string
  encounter_id?: string
  service_date: string
  diagnosis_codes?: string[]
  procedure_codes?: string[]
  total_amount: number
}

export interface ClaimUpdate {
  approved_amount?: number
  paid_amount?: number
  patient_responsibility?: number
  status?: string
  denial_reason?: string
}

export interface PriorAuth {
  id: string
  patient_id: string
  coverage_id: string
  service_type: string
  procedure_codes?: string[] | null
  clinical_justification?: string | null
  requested_by: string
  status: string
  decision?: string | null
  approved_units?: number | null
  valid_from?: string | null
  valid_to?: string | null
  decided_by?: string | null
  decided_at?: string | null
  denial_reason?: string | null
  created_at: string
  updated_at: string
  model_version: number
}

export interface PriorAuthCreate {
  patient_id: string
  coverage_id: string
  service_type: string
  procedure_codes?: string[]
  clinical_justification?: string
  requested_by: string
}

export interface PriorAuthDecision {
  decision: 'APPROVED' | 'DENIED'
  approved_units?: number
  valid_from?: string
  valid_to?: string
  denial_reason?: string
  decided_by: string
}

// ---- reporting-service ---------------------------------------------------------

export interface ReportDefinition {
  id: string
  name: string
  report_type: string
  description?: string | null
  parameters_schema?: Record<string, unknown> | null
  is_active: boolean
  status: string
  created_at: string
  updated_at: string
  model_version: number
}

export interface ReportDefinitionCreate {
  name: string
  report_type: string
  description?: string
  parameters_schema?: Record<string, unknown>
  is_active?: boolean
}

export interface ReportInstance {
  id: string
  report_definition_id: string
  parameters?: Record<string, unknown> | null
  requested_by: string
  status: string
  result_data?: Record<string, unknown> | null
  result_url?: string | null
  error_message?: string | null
  started_at?: string | null
  completed_at?: string | null
  created_at: string
  updated_at: string
  model_version: number
}

export interface ReportInstanceCreate {
  report_definition_id: string
  parameters?: Record<string, unknown>
  requested_by: string
}

export interface ScheduledReport {
  id: string
  report_definition_id: string
  schedule_cron: string
  parameters?: Record<string, unknown> | null
  delivery_email?: string | null
  is_active: boolean
  last_run_at?: string | null
  next_run_at?: string | null
  created_at: string
  updated_at: string
  model_version: number
}

export interface ScheduledReportCreate {
  report_definition_id: string
  schedule_cron: string
  parameters?: Record<string, unknown>
  delivery_email?: string
  is_active?: boolean
}