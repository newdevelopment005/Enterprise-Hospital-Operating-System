// Shared types for the EHOS Executive Command Center.

export type KpiFormat = 'number' | 'currency' | 'percent' | 'minutes'
export type KpiStatus = 'ok' | 'warn' | 'alert'

export interface KpiValue {
  key: string
  label: string
  value: number
  format: KpiFormat
  deltaPct: number
  goodWhen: 'up' | 'down'
  status: KpiStatus
  hint: string
  spark: number[]
  asOf: string
}

export interface SeriesPoint {
  t: string
  v: number
}

export interface Series {
  key: string
  label: string
  unit: string
  color: string
  points: SeriesPoint[]
}

export interface Datasets {
  kpis: KpiValue[]
  admissions: Series
  discharges: Series
  revenue: Series
  expenses: Series
  occupancy: Series
  utilization: Series
  waiting: Series
  mortality: Series
  readmission: Series
  inventory: Series
}

// --- analytics-service (live multi-department data + locale) ------------------

export interface LocaleInfo {
  countryCode: string
  countryName: string
  currencyCode: string
  currencySymbol: string
  timezone: string
  localeTag: string
  exchangeRate: number
  utcOffset: string
  localTimeIso: string
  detectedAt: string
  resolution?: string
}

export interface DepartmentKpis {
  code: string
  name: string
  kpis: KpiValue[]
}

export interface AnalyticsOverview {
  source: string
  locale: LocaleInfo
  kpis: KpiValue[]
  series: Record<string, Series>
  departments: DepartmentKpis[]
  generatedAt: string
}

// --- forecast (prediction-service contract §8) -------------------------------

export interface Forecast {
  predictionKey: string
  entityType: string
  label: string
  horizon: string
  windowFrom: string
  windowTo: string
  value: number[]
  q10: number[]
  q90: number[]
  confidence: number
  modelVersion: string
  generatedAt: string
  source: 'prediction-service' | 'demo'
  unit: string
}

// --- AI insights -------------------------------------------------------------

export interface Insight {
  text: string
  category: 'rule' | 'ai'
}

// --- API envelopes -----------------------------------------------------------

export interface ApiEnvelope<T> {
  success: boolean
  data: T
  statusCode?: number
  message?: string
  errorCode?: string
}

export interface ForecastServing {
  prediction_key: string
  entity_type: string | null
  entity_id: string | null
  horizon: string | null
  window_from: string | null
  window_to: string | null
  forecast: { value: number[]; q10: number[]; q90: number[] }
  confidence: number | null
  model_version: string
  generated_at: string
  sources: string[]
}

export interface ForecastTarget {
  key: string
  entity_type: string
  horizon: string
  metric: string
  gate: number
  description: string
}

export interface ChatRequest {
  message: string
  user_id: string
  model_key?: string
  use_rag?: boolean
  request_type?: string
}

export interface ChatResponse {
  answer: string
  request_id: string
  conversation_id: string
  model_key: string
  sources: unknown[]
  retrieved: boolean
  tokens_in: number
  tokens_out: number
  latency_ms: number
}