// Typed client for the ehr-service REST API (envelope-aware).

import type {
  Allergy,
  AllergyIn,
  ApiEnvelope,
  Appointment,
  AppointmentIn,
  AvailabilitySlot,
  ClinicalNote,
  ClinicalOrder,
  Diagnosis,
  DiagnosisIn,
  Encounter,
  LabOrder,
  LabOrderCreate,
  LabOrderUpdate,
  LabResult,
  LabResultCreate,
  LabResultUpdate,
  LabResultVerify,
  LabTest,
  LabTestCreate,
  MedicalAlert,
  MedicalHistoryEntry,
  MedicalHistoryIn,
  Medication,
  MedicationIn,
  Modality,
  ModalityCreate,
  NoteIn,
  OrderIn,
  PaginatedResponse,
  PatientChart,
  PatientDetail,
  PatientSummary,
  PharmacyMedication,
  Problem,
  ProblemIn,
  Queue,
  QueueBoard,
  QueueEntry,
  RadiologyOrder,
  RadiologyOrderCreate,
  RadiologyOrderUpdate,
  RadiologyReport,
  RadiologyReportCreate,
  RadiologyReportUpdate,
  StockBatch,
  Prescription,
  PrescriptionIn,
  DispensingRecord,
  Sample,
  SampleCreate,
  SampleCollect,
  SampleReceive,
  SampleReject,
  SoapNoteIn,
  Study,
  StudyCreate,
  TimelineEntry,
  Vital,
  VitalIn,
  Charge,
  ChargeIn,
  Invoice,
  PatientAllergy,
  PatientBillingSummary,
  InventoryItem,
  InventoryItemCreate,
  StockItem,
  StockItemCreate,
  StockMovement,
  StockMovementCreate,
  ReorderAlert,
  WorkflowDefinition,
  WorkflowDefinitionCreate,
  WorkflowInstance,
  WorkflowInstanceCreate,
  WorkflowTransition,
  WorkflowEventFire,
  ClinicalNoteDoc,
  ClinicalNoteDocCreate,
  DocNoteVersion,
  DocTemplate,
  DocTemplateCreate,
  Coverage,
  CoverageCreate,
  Claim,
  ClaimCreate,
  ClaimUpdate,
  PriorAuth,
  PriorAuthCreate,
  PriorAuthDecision,
  ReportDefinition,
  ReportDefinitionCreate,
  ReportInstance,
  ReportInstanceCreate,
  ScheduledReport,
  ScheduledReportCreate,
} from './types'

const BASE = '/api/v1/ehr/patients'

async function parseEnvelope<T>(response: Response): Promise<ApiEnvelope<T>> {
  const text = await response.text()
  if (!text.trim()) {
    throw new Error(`Backend service unavailable (HTTP ${response.status}) — is ehr-service running on port 8502?`)
  }
  try {
    return JSON.parse(text) as ApiEnvelope<T>
  } catch {
    throw new Error(`Backend returned an invalid response (HTTP ${response.status})`)
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const envelope = await parseEnvelope<T>(response)
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}

// Some module services return their response models directly (no envelope).
async function rawRequest<T>(base: string, path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const text = await response.text()
  if (!text.trim()) {
    if (response.ok) return undefined as T
    throw new Error(`HTTP ${response.status}`)
  }
  let body: unknown
  try {
    body = JSON.parse(text)
  } catch {
    throw new Error(`Backend returned an invalid response (HTTP ${response.status})`)
  }
  if (!response.ok) {
    const err = body as { detail?: string; message?: string; errorCode?: string }
    throw new Error(err.detail ?? err.message ?? err.errorCode ?? `Request failed (HTTP ${response.status})`)
  }
  return body as T
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

const MPI_BASE = '/mpi/api/v1/patients'

async function mpiRequest<T>(path: string): Promise<T> {
  const response = await fetch(`${MPI_BASE}${path}`)
  const envelope = await parseEnvelope<T>(response)
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}

export const mpiApi = {
  search(q: string): Promise<{ patients: PatientSummary[]; total: number }> {
    return mpiRequest(`?q=${encodeURIComponent(q)}&limit=20`)
  },
  get(patientId: string): Promise<PatientDetail> {
    return mpiRequest(`/${patientId}`)
  },
  alerts(patientId: string, activeOnly = true): Promise<{ items: MedicalAlert[]; total: number }> {
    return mpiRequest(`/${patientId}/alerts?active_only=${activeOnly}`)
  },
}

const SCHED_BASE = '/sched/api/v1/appointments'

async function schedRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${SCHED_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const envelope = await parseEnvelope<T>(response)
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}

export const appointmentsApi = {
  book(payload: AppointmentIn): Promise<Appointment> {
    return schedRequest('', { method: 'POST', body: JSON.stringify(payload) })
  },
  list(patientId: string, upcomingOnly = false): Promise<{ appointments: Appointment[]; total: number }> {
    const params = new URLSearchParams({ patient_id: patientId })
    if (upcomingOnly) params.set('upcoming', 'true')
    return schedRequest(`?${params.toString()}`)
  },
  get(appointmentId: string): Promise<Appointment> {
    return schedRequest(`/${appointmentId}`)
  },
  reschedule(appointmentId: string, startTime: string, durationMin?: number): Promise<Appointment> {
    return schedRequest(`/${appointmentId}/reschedule`, {
      method: 'POST',
      body: JSON.stringify(durationMin ? { start_time: startTime, duration_min: durationMin } : { start_time: startTime }),
    })
  },
  cancel(appointmentId: string, reason?: string): Promise<Appointment> {
    return schedRequest(`/${appointmentId}/cancel`, {
      method: 'POST',
      body: JSON.stringify(reason ? { reason } : {}),
    })
  },
  complete(appointmentId: string): Promise<Appointment> {
    return schedRequest(`/${appointmentId}/complete`, { method: 'POST', body: '{}' })
  },
  noShow(appointmentId: string): Promise<Appointment> {
    return schedRequest(`/${appointmentId}/no-show`, { method: 'POST', body: '{}' })
  },
  availability(day: string, providerId?: string): Promise<{ slots: AvailabilitySlot[]; free: number; total: number }> {
    const params = new URLSearchParams({ day })
    if (providerId) params.set('provider_id', providerId)
    return schedRequest(`/availability?${params.toString()}`)
  },
}

const QUEUE_BASE = '/q/api/v1/queues'

async function queueRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${QUEUE_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const envelope = await parseEnvelope<T>(response)
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}

export const queuesApi = {
  list(activeOnly = true): Promise<{ queues: Queue[]; total: number }> {
    return queueRequest(`?active_only=${activeOnly}`)
  },
  create(queueType: string, name?: string): Promise<Queue> {
    return queueRequest('', { method: 'POST', body: JSON.stringify({ queue_type: queueType, name }) })
  },
  board(queueId: string): Promise<QueueBoard> {
    return queueRequest(`/board/${queueId}`)
  },
  join(queueId: string, patientId: string, priority = 0): Promise<QueueEntry> {
    return queueRequest(`/${queueId}/entries`, {
      method: 'POST',
      body: JSON.stringify({ patient_id: patientId, priority }),
    })
  },
  advance(queueId: string): Promise<QueueEntry> {
    return queueRequest(`/${queueId}/advance`, { method: 'POST', body: '{}' })
  },
  start(entryId: string): Promise<QueueEntry> {
    return queueRequest(`/entries/${entryId}/start`, { method: 'POST', body: '{}' })
  },
  complete(entryId: string): Promise<QueueEntry> {
    return queueRequest(`/entries/${entryId}/complete`, { method: 'POST', body: '{}' })
  },
  cancel(entryId: string): Promise<QueueEntry> {
    return queueRequest(`/entries/${entryId}/cancel`, { method: 'POST', body: '{}' })
  },
}

const BILL_BASE = '/bill/api/v1/billing'

async function billRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BILL_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const envelope = await parseEnvelope<T>(response)
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}

const CHARGE_TYPES = ['CONSULTATION', 'LAB', 'RADIOLOGY', 'MEDICATION', 'PROCEDURE', 'ROOM', 'OTHER'] as const
export type ChargeType = (typeof CHARGE_TYPES)[number]
export { CHARGE_TYPES }

export const billingApi = {
  addCharge(payload: ChargeIn): Promise<Charge> {
    return billRequest('/charges', { method: 'POST', body: JSON.stringify(payload) })
  },
  listCharges(patientId: string): Promise<{ charges: Charge[]; total: number }> {
    return billRequest(`/charges?patient_id=${encodeURIComponent(patientId)}`)
  },
  createInvoice(patientId: string, insuranceAmount?: number): Promise<Invoice> {
    return billRequest('/invoices', {
      method: 'POST',
      body: JSON.stringify({
        patient_id: patientId,
        ...(insuranceAmount ? { insurance_amount: insuranceAmount } : {}),
      }),
    })
  },
  invoice(invoiceId: string): Promise<Invoice> {
    return billRequest(`/invoices/${invoiceId}`)
  },
  pay(invoiceId: string, amount: number, method: string): Promise<{ receipt_number: string }> {
    return billRequest('/payments', {
      method: 'POST',
      body: JSON.stringify({ invoice_id: invoiceId, amount, payment_method: method }),
    })
  },
  summary(patientId: string): Promise<PatientBillingSummary> {
    return billRequest(`/patients/${patientId}/summary`)
  },
}

const RX_BASE = '/rx/api/v1/prescriptions'

async function rxRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${RX_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const envelope = await parseEnvelope<T>(response)
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}

export const prescriptionsApi = {
  create(payload: PrescriptionIn): Promise<Prescription> {
    return rxRequest('', { method: 'POST', body: JSON.stringify(payload) })
  },
  list(patientId: string): Promise<{ prescriptions: Prescription[]; total: number }> {
    return rxRequest(`?patient_id=${encodeURIComponent(patientId)}`)
  },
  get(rxId: string): Promise<Prescription> {
    return rxRequest(`/${rxId}`)
  },
  cancel(rxId: string, reason: string): Promise<Prescription> {
    return rxRequest(`/${rxId}/cancel`, { method: 'POST', body: JSON.stringify({ reason }) })
  },
  complete(rxId: string): Promise<Prescription> {
    return rxRequest(`/${rxId}/complete`, { method: 'POST', body: '{}' })
  },
  allergies(patientId: string): Promise<{ items: PatientAllergy[]; total: number }> {
    return rxRequest(`/patients/${patientId}/allergies`)
  },
  addAllergy(
    patientId: string,
    payload: { allergen: string; allergen_type: string; severity: string; recorded_by: string },
  ): Promise<PatientAllergy> {
    return rxRequest(`/patients/${patientId}/allergies`, {
      method: 'POST',
      body: JSON.stringify({ ...payload, patient_id: patientId }),
    })
  },
}

const PHARM_BASE = '/pharm/api/v1/pharmacy'

async function pharmRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${PHARM_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const envelope = await parseEnvelope<T>(response)
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}

export const pharmacyApi = {
  searchMedications(q = ''): Promise<{ medications: PharmacyMedication[]; total: number }> {
    return pharmRequest(`/medications?q=${encodeURIComponent(q)}`)
  },
  createMedication(payload: { code: string; name: string; form?: string; controlled?: boolean }): Promise<PharmacyMedication> {
    return pharmRequest('/medications', { method: 'POST', body: JSON.stringify(payload) })
  },
  stock(medicationId: string): Promise<{ medication: PharmacyMedication; total: number; batches: StockBatch[] }> {
    return pharmRequest(`/medications/${medicationId}/stock`)
  },
  receiveStock(payload: { medication_id: string; batch_number: string; expiry_date: string; quantity: number }): Promise<unknown> {
    return pharmRequest('/stock/receive', { method: 'POST', body: JSON.stringify(payload) })
  },
  expiring(days = 90): Promise<{ items: Array<StockBatch & { medication_name: string }>; total: number }> {
    return pharmRequest(`/stock/expiring?days=${days}`)
  },
  dispense(payload: {
    patient_id: string
    medication_id: string
    quantity: number
    dispensed_by: string
    prescription_id?: string
  }): Promise<DispensingRecord> {
    return pharmRequest('/dispense', { method: 'POST', body: JSON.stringify({ ...payload, location: 'MAIN' }) })
  },
  history(patientId: string): Promise<{ items: DispensingRecord[]; total: number }> {
    return pharmRequest(`/patients/${patientId}/dispensing`)
  },
}

const LAB_BASE = '/lab/api/v1/laboratory'

async function labRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  return rawRequest<T>(LAB_BASE, path, options)
}

export const laboratoryApi = {
  // Lab Tests
  listTests(category?: string, activeOnly = true): Promise<PaginatedResponse<LabTest>> {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (!activeOnly) params.set('active_only', 'false')
    return labRequest(`/tests?${params.toString()}`)
  },
  getTest(testId: string): Promise<LabTest> {
    return labRequest(`/tests/${testId}`)
  },
  createTest(payload: LabTestCreate): Promise<LabTest> {
    return labRequest('/tests', { method: 'POST', body: JSON.stringify(payload) })
  },
  updateTest(testId: string, payload: Partial<LabTestCreate>): Promise<LabTest> {
    return labRequest(`/tests/${testId}`, { method: 'PATCH', body: JSON.stringify(payload) })
  },
  deleteTest(testId: string): Promise<void> {
    return labRequest(`/tests/${testId}`, { method: 'DELETE' })
  },

  // Lab Orders
  listOrders(patientId?: string, doctorId?: string, status?: string): Promise<PaginatedResponse<LabOrder>> {
    const params = new URLSearchParams()
    if (patientId) params.set('patient_id', patientId)
    if (doctorId) params.set('ordering_doctor', doctorId)
    if (status) params.set('status', status)
    return labRequest(`/orders?${params.toString()}`)
  },
  getOrder(orderId: string): Promise<LabOrder> {
    return labRequest(`/orders/${orderId}`)
  },
  createOrder(payload: LabOrderCreate): Promise<LabOrder> {
    return labRequest('/orders', { method: 'POST', body: JSON.stringify(payload) })
  },
  updateOrder(orderId: string, payload: LabOrderUpdate): Promise<LabOrder> {
    return labRequest(`/orders/${orderId}`, { method: 'PATCH', body: JSON.stringify(payload) })
  },
  cancelOrder(orderId: string): Promise<LabOrder> {
    return labRequest(`/orders/${orderId}/cancel`, { method: 'POST', body: '{}' })
  },

  // Samples
  createSample(payload: SampleCreate): Promise<Sample> {
    return labRequest('/samples', { method: 'POST', body: JSON.stringify(payload) })
  },
  collectSample(sampleId: string, payload: SampleCollect): Promise<Sample> {
    return labRequest(`/samples/${sampleId}/collect`, { method: 'POST', body: JSON.stringify(payload) })
  },
  receiveSample(sampleId: string, payload: SampleReceive): Promise<Sample> {
    return labRequest(`/samples/${sampleId}/receive`, { method: 'POST', body: JSON.stringify(payload) })
  },
  rejectSample(sampleId: string, payload: SampleReject): Promise<Sample> {
    return labRequest(`/samples/${sampleId}/reject`, { method: 'POST', body: JSON.stringify(payload) })
  },

  // Lab Results
  listResults(patientId?: string, orderItemId?: string, testId?: string, status?: string): Promise<PaginatedResponse<LabResult>> {
    const params = new URLSearchParams()
    if (patientId) params.set('patient_id', patientId)
    if (orderItemId) params.set('order_item_id', orderItemId)
    if (testId) params.set('test_id', testId)
    if (status) params.set('status', status)
    return labRequest(`/results?${params.toString()}`)
  },
  getResult(resultId: string): Promise<LabResult> {
    return labRequest(`/results/${resultId}`)
  },
  createResult(payload: LabResultCreate): Promise<LabResult> {
    return labRequest('/results', { method: 'POST', body: JSON.stringify(payload) })
  },
  updateResult(resultId: string, payload: LabResultUpdate): Promise<LabResult> {
    return labRequest(`/results/${resultId}`, { method: 'PATCH', body: JSON.stringify(payload) })
  },
  verifyResult(resultId: string, payload: LabResultVerify): Promise<LabResult> {
    return labRequest(`/results/${resultId}/verify`, { method: 'POST', body: JSON.stringify(payload) })
  },
  cancelResult(resultId: string): Promise<LabResult> {
    return labRequest(`/results/${resultId}/cancel`, { method: 'POST', body: '{}' })
  },
}

const RAD_BASE = '/rad/api/v1/radiology'

async function radRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  return rawRequest<T>(RAD_BASE, path, options)
}

export const radiologyApi = {
  // Modalities
  listModalities(activeOnly = true): Promise<PaginatedResponse<Modality>> {
    return radRequest(`/modalities?active_only=${activeOnly}`)
  },
  createModality(payload: ModalityCreate): Promise<Modality> {
    return radRequest('/modalities', { method: 'POST', body: JSON.stringify(payload) })
  },

  // Orders
  listOrders(patientId?: string, doctorId?: string, status?: string): Promise<PaginatedResponse<RadiologyOrder>> {
    const params = new URLSearchParams()
    if (patientId) params.set('patient_id', patientId)
    if (doctorId) params.set('ordering_doctor', doctorId)
    if (status) params.set('status', status)
    return radRequest(`/orders?${params.toString()}`)
  },
  getOrder(orderId: string): Promise<RadiologyOrder> {
    return radRequest(`/orders/${orderId}`)
  },
  createOrder(payload: RadiologyOrderCreate): Promise<RadiologyOrder> {
    return radRequest('/orders', { method: 'POST', body: JSON.stringify(payload) })
  },
  updateOrder(orderId: string, payload: RadiologyOrderUpdate): Promise<RadiologyOrder> {
    return radRequest(`/orders/${orderId}`, { method: 'PATCH', body: JSON.stringify(payload) })
  },
  cancelOrder(orderId: string): Promise<RadiologyOrder> {
    return radRequest(`/orders/${orderId}/cancel`, { method: 'POST', body: '{}' })
  },

  // Studies
  createStudy(payload: StudyCreate): Promise<Study> {
    return radRequest('/studies', { method: 'POST', body: JSON.stringify(payload) })
  },
  startStudy(studyId: string, performedBy: string): Promise<Study> {
    return radRequest(`/studies/${studyId}/start`, { method: 'POST', body: JSON.stringify({ performed_by: performedBy }) })
  },
  completeStudy(studyId: string, notes?: string): Promise<Study> {
    return radRequest(`/studies/${studyId}/complete`, { method: 'POST', body: JSON.stringify({ technician_notes: notes }) })
  },

  // Reports
  listReports(patientId?: string, orderId?: string, status?: string): Promise<PaginatedResponse<RadiologyReport>> {
    const params = new URLSearchParams()
    if (patientId) params.set('patient_id', patientId)
    if (orderId) params.set('order_id', orderId)
    if (status) params.set('status', status)
    return radRequest(`/reports?${params.toString()}`)
  },
  createReport(payload: RadiologyReportCreate): Promise<RadiologyReport> {
    return radRequest('/reports', { method: 'POST', body: JSON.stringify(payload) })
  },
  updateReport(reportId: string, payload: RadiologyReportUpdate): Promise<RadiologyReport> {
    return radRequest(`/reports/${reportId}`, { method: 'PATCH', body: JSON.stringify(payload) })
  },
  signReport(reportId: string, signedBy: string): Promise<RadiologyReport> {
    return radRequest(`/reports/${reportId}/sign`, { method: 'POST', body: JSON.stringify({ signed_by: signedBy }) })
  },
}

const INV_BASE = '/inv/api/v1/inventory'

export const inventoryApi = {
  // Items
  listItems(category?: string, activeOnly = true): Promise<PaginatedResponse<InventoryItem>> {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (!activeOnly) params.set('active_only', 'false')
    return rawRequest(INV_BASE, `/items?${params.toString()}`)
  },
  createItem(payload: InventoryItemCreate): Promise<InventoryItem> {
    return rawRequest(INV_BASE, '/items', { method: 'POST', body: JSON.stringify(payload) })
  },

  // Stock
  createStock(payload: StockItemCreate): Promise<StockItem> {
    return rawRequest(INV_BASE, '/stock', { method: 'POST', body: JSON.stringify(payload) })
  },
  listStock(itemId?: string, location?: string): Promise<PaginatedResponse<StockItem>> {
    const params = new URLSearchParams()
    if (itemId) params.set('item_id', itemId)
    if (location) params.set('location', location)
    return rawRequest(INV_BASE, `/stock?${params.toString()}`)
  },
  expiring(withinDays = 30): Promise<StockItem[]> {
    return rawRequest(INV_BASE, `/expiring?within_days=${withinDays}`)
  },

  // Movements
  receive(stockId: string, payload: StockMovementCreate): Promise<StockMovement> {
    return rawRequest(INV_BASE, `/stock/${stockId}/receive`, { method: 'POST', body: JSON.stringify(payload) })
  },
  dispense(stockId: string, payload: StockMovementCreate): Promise<StockMovement> {
    return rawRequest(INV_BASE, `/stock/${stockId}/dispense`, { method: 'POST', body: JSON.stringify(payload) })
  },
  listMovements(stockItemId?: string, movementType?: string): Promise<PaginatedResponse<StockMovement>> {
    const params = new URLSearchParams()
    if (stockItemId) params.set('stock_item_id', stockItemId)
    if (movementType) params.set('movement_type', movementType)
    return rawRequest(INV_BASE, `/movements?${params.toString()}`)
  },

  // Reorder alerts
  listAlerts(status?: string): Promise<PaginatedResponse<ReorderAlert>> {
    const params = status ? `?status=${encodeURIComponent(status)}` : ''
    return rawRequest(INV_BASE, `/reorder-alerts${params}`)
  },
  resolveAlert(alertId: string): Promise<ReorderAlert> {
    return rawRequest(INV_BASE, `/reorder-alerts/${alertId}/resolve`, { method: 'POST', body: '{}' })
  },
}

// ---- workflow-service ---------------------------------------------------------

const WF_BASE = '/wf/api/v1/workflows'

export const workflowApi = {
  // Definitions
  listDefinitions(activeOnly = true): Promise<PaginatedResponse<WorkflowDefinition>> {
    return rawRequest(WF_BASE, `/definitions?active_only=${activeOnly}`)
  },
  createDefinition(payload: WorkflowDefinitionCreate): Promise<WorkflowDefinition> {
    return rawRequest(WF_BASE, '/definitions', { method: 'POST', body: JSON.stringify(payload) })
  },

  // Instances
  listInstances(patientId?: string, status?: string): Promise<PaginatedResponse<WorkflowInstance>> {
    const params = new URLSearchParams()
    if (patientId) params.set('patient_id', patientId)
    if (status) params.set('status', status)
    return rawRequest(WF_BASE, `/instances?${params.toString()}`)
  },
  createInstance(payload: WorkflowInstanceCreate): Promise<WorkflowInstance> {
    return rawRequest(WF_BASE, '/instances', { method: 'POST', body: JSON.stringify(payload) })
  },
  fireEvent(instanceId: string, payload: WorkflowEventFire): Promise<WorkflowInstance> {
    return rawRequest(WF_BASE, `/instances/${instanceId}/fire`, { method: 'POST', body: JSON.stringify(payload) })
  },
  cancelInstance(instanceId: string): Promise<WorkflowInstance> {
    return rawRequest(WF_BASE, `/instances/${instanceId}/cancel`, { method: 'POST', body: '{}' })
  },
  pauseInstance(instanceId: string): Promise<WorkflowInstance> {
    return rawRequest(WF_BASE, `/instances/${instanceId}/pause`, { method: 'POST', body: '{}' })
  },
  resumeInstance(instanceId: string): Promise<WorkflowInstance> {
    return rawRequest(WF_BASE, `/instances/${instanceId}/resume`, { method: 'POST', body: '{}' })
  },
  transitions(instanceId: string): Promise<WorkflowTransition[]> {
    return rawRequest(WF_BASE, `/instances/${instanceId}/transitions`)
  },
}

// ---- clinical-documentation-service -------------------------------------------

const DOC_BASE = '/doc/api/v1/documentation'

export const documentationApi = {
  // Notes
  listNotes(patientId?: string, noteType?: string, status?: string): Promise<PaginatedResponse<ClinicalNoteDoc>> {
    const params = new URLSearchParams()
    if (patientId) params.set('patient_id', patientId)
    if (noteType) params.set('note_type', noteType)
    if (status) params.set('status', status)
    return rawRequest(DOC_BASE, `/notes?${params.toString()}`)
  },
  createNote(payload: ClinicalNoteDocCreate): Promise<ClinicalNoteDoc> {
    return rawRequest(DOC_BASE, '/notes', { method: 'POST', body: JSON.stringify(payload) })
  },
  signNote(noteId: string, signedBy: string): Promise<ClinicalNoteDoc> {
    return rawRequest(DOC_BASE, `/notes/${noteId}/sign`, { method: 'POST', body: JSON.stringify({ signed_by: signedBy }) })
  },
  cancelNote(noteId: string): Promise<ClinicalNoteDoc> {
    return rawRequest(DOC_BASE, `/notes/${noteId}/cancel`, { method: 'POST', body: '{}' })
  },
  noteVersions(noteId: string): Promise<DocNoteVersion[]> {
    return rawRequest(DOC_BASE, `/notes/${noteId}/versions`)
  },

  // Templates
  listTemplates(noteType?: string, activeOnly = true): Promise<PaginatedResponse<DocTemplate>> {
    const params = new URLSearchParams()
    if (noteType) params.set('note_type', noteType)
    if (!activeOnly) params.set('active_only', 'false')
    return rawRequest(DOC_BASE, `/templates?${params.toString()}`)
  },
  createTemplate(payload: DocTemplateCreate): Promise<DocTemplate> {
    return rawRequest(DOC_BASE, '/templates', { method: 'POST', body: JSON.stringify(payload) })
  },
}

// ---- insurance-service ---------------------------------------------------------

const INS_BASE = '/ins/api/v1/insurance'

export const insuranceApi = {
  // Coverages
  listCoverages(patientId?: string, activeOnly = true): Promise<PaginatedResponse<Coverage>> {
    const params = new URLSearchParams()
    if (patientId) params.set('patient_id', patientId)
    if (!activeOnly) params.set('active_only', 'false')
    return rawRequest(INS_BASE, `/coverages?${params.toString()}`)
  },
  createCoverage(payload: CoverageCreate): Promise<Coverage> {
    return rawRequest(INS_BASE, '/coverages', { method: 'POST', body: JSON.stringify(payload) })
  },

  // Claims
  listClaims(patientId?: string, status?: string): Promise<PaginatedResponse<Claim>> {
    const params = new URLSearchParams()
    if (patientId) params.set('patient_id', patientId)
    if (status) params.set('status', status)
    return rawRequest(INS_BASE, `/claims?${params.toString()}`)
  },
  createClaim(payload: ClaimCreate): Promise<Claim> {
    return rawRequest(INS_BASE, '/claims', { method: 'POST', body: JSON.stringify(payload) })
  },
  submitClaim(claimId: string): Promise<Claim> {
    return rawRequest(INS_BASE, `/claims/${claimId}/submit`, { method: 'POST', body: '{}' })
  },
  updateClaim(claimId: string, payload: ClaimUpdate): Promise<Claim> {
    return rawRequest(INS_BASE, `/claims/${claimId}`, { method: 'PATCH', body: JSON.stringify(payload) })
  },

  // Prior authorizations
  listPriorAuths(patientId?: string, status?: string): Promise<PaginatedResponse<PriorAuth>> {
    const params = new URLSearchParams()
    if (patientId) params.set('patient_id', patientId)
    if (status) params.set('status', status)
    return rawRequest(INS_BASE, `/prior-authorizations?${params.toString()}`)
  },
  createPriorAuth(payload: PriorAuthCreate): Promise<PriorAuth> {
    return rawRequest(INS_BASE, '/prior-authorizations', { method: 'POST', body: JSON.stringify(payload) })
  },
  decidePriorAuth(priorAuthId: string, payload: PriorAuthDecision): Promise<PriorAuth> {
    return rawRequest(INS_BASE, `/prior-authorizations/${priorAuthId}/decide`, { method: 'POST', body: JSON.stringify(payload) })
  },
}

// ---- reporting-service ---------------------------------------------------------

const RPT_BASE = '/rpt/api/v1/reporting'

export const reportingApi = {
  // Definitions
  listDefinitions(reportType?: string, activeOnly = true): Promise<PaginatedResponse<ReportDefinition>> {
    const params = new URLSearchParams()
    if (reportType) params.set('report_type', reportType)
    if (!activeOnly) params.set('active_only', 'false')
    return rawRequest(RPT_BASE, `/definitions?${params.toString()}`)
  },
  createDefinition(payload: ReportDefinitionCreate): Promise<ReportDefinition> {
    return rawRequest(RPT_BASE, '/definitions', { method: 'POST', body: JSON.stringify(payload) })
  },

  // Instances
  listInstances(definitionId?: string, status?: string): Promise<PaginatedResponse<ReportInstance>> {
    const params = new URLSearchParams()
    if (definitionId) params.set('definition_id', definitionId)
    if (status) params.set('status', status)
    return rawRequest(RPT_BASE, `/instances?${params.toString()}`)
  },
  createInstance(payload: ReportInstanceCreate): Promise<ReportInstance> {
    return rawRequest(RPT_BASE, '/instances', { method: 'POST', body: JSON.stringify(payload) })
  },
  startInstance(instanceId: string): Promise<ReportInstance> {
    return rawRequest(RPT_BASE, `/instances/${instanceId}/start`, { method: 'POST', body: '{}' })
  },
  completeInstance(instanceId: string): Promise<ReportInstance> {
    return rawRequest(RPT_BASE, `/instances/${instanceId}/complete`, { method: 'POST', body: '{}' })
  },

  // Scheduled reports
  listScheduled(activeOnly = true): Promise<PaginatedResponse<ScheduledReport>> {
    return rawRequest(RPT_BASE, `/scheduled?active_only=${activeOnly}`)
  },
  createScheduled(payload: ScheduledReportCreate): Promise<ScheduledReport> {
    return rawRequest(RPT_BASE, '/scheduled', { method: 'POST', body: JSON.stringify(payload) })
  },
  deactivateScheduled(scheduledId: string): Promise<ScheduledReport> {
    return rawRequest(RPT_BASE, `/scheduled/${scheduledId}/deactivate`, { method: 'POST', body: '{}' })
  },
}