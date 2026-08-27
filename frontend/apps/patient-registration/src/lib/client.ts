// Thin typed client for the patient-service REST API. Extraction matches the
// EHOS envelope: { success, data } / { success:false, errorCode, message }.

import type {
  ApiEnvelope,
  Insurance,
  MedicalAlert,
  PatientDetail,
  RegisterPatient,
  SearchResult,
  TimelineEntry,
} from './types'

const BASE = '/api/v1/patients'

async function parseEnvelope<T>(response: Response): Promise<ApiEnvelope<T>> {
  const text = await response.text()
  if (!text.trim()) {
    throw new Error(`Backend service unavailable (HTTP ${response.status}) — is patient-service running on port 8501?`)
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
  if (!envelope.success) {
    throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  }
  return envelope.data
}

export const patientApi = {
  register(payload: RegisterPatient): Promise<PatientDetail> {
    return request<PatientDetail>('', { method: 'POST', body: JSON.stringify(payload) })
  },

  search(q: string, limit = 50, includeInactive = false): Promise<SearchResult> {
    const params = new URLSearchParams({ q, limit: String(limit), includeInactive: String(includeInactive) })
    return request<SearchResult>(`?${params.toString()}`)
  },

  get(id: string): Promise<PatientDetail> {
    return request<PatientDetail>(`/${id}`)
  },

  update(id: string, patch: Record<string, unknown>): Promise<PatientDetail> {
    return request<PatientDetail>(`/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })
  },

  timeline(id: string): Promise<TimelineEntry[]> {
    return request<TimelineEntry[]>(`/${id}/timeline`)
  },

  addAlert(id: string, alert: MedicalAlert): Promise<unknown> {
    return request(`/${id}/alerts`, { method: 'POST', body: JSON.stringify(alert) })
  },

  resolveAlert(id: string, alertId: string, reason?: string): Promise<unknown> {
    const params = reason ? `?reason=${encodeURIComponent(reason)}` : ''
    return request(`/${id}/alerts/${alertId}/resolve${params}`, { method: 'POST' })
  },

  addInsurance(id: string, insurance: Insurance): Promise<unknown> {
    return request(`/${id}/insurance`, { method: 'POST', body: JSON.stringify(insurance) })
  },

  addBiometric(id: string, modality: string, state = 'READY'): Promise<unknown> {
    return request(`/${id}/biometrics`, {
      method: 'POST',
      body: JSON.stringify({ modality, enrollmentState: state }),
    })
  },

  addPhoto(id: string, dataB64: string, contentType = 'image/jpeg'): Promise<unknown> {
    return request(`/${id}/photo`, {
      method: 'POST',
      body: JSON.stringify({ contentType, dataB64 }),
    })
  },

  merge(survivorId: string, duplicateId: string): Promise<unknown> {
    const params = new URLSearchParams({ survivor_id: survivorId, duplicate_id: duplicateId })
    return request<unknown>(`/merge?${params.toString()}`, { method: 'POST' })
  },
}