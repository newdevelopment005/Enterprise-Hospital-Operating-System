// Typed clients for the prediction-service and ai-service REST APIs.
//
// Both are optional at runtime: the dashboard degrades to demo data when a
// service is unavailable, so every request here is wrapped in try/catch.

import type {
  AnalyticsOverview,
  ApiEnvelope,
  ChatRequest,
  ChatResponse,
  ForecastServing,
  ForecastTarget,
  LocaleInfo,
} from './types'
import { getValidToken } from './auth'

const PREDICTIONS = '/api/v1/predictions'
const AI = '/api/v1/ai'
const ANALYTICS = '/api/v1/analytics'

async function envelopeOf<T>(response: Response): Promise<T> {
  const text = await response.text()
  if (!text.trim()) {
    throw new Error(`Backend service unavailable (HTTP ${response.status})`)
  }
  let body: ApiEnvelope<T>
  try {
    body = JSON.parse(text) as ApiEnvelope<T>
  } catch {
    throw new Error(`Backend returned an invalid response (HTTP ${response.status})`)
  }
  if (!body.success) throw new Error(body.message || body.errorCode || 'Request failed')
  return body.data
}

export const forecastsApi = {
  async targets(): Promise<ForecastTarget[]> {
    const response = await fetch(`${PREDICTIONS}/targets`)
    return envelopeOf<ForecastTarget[]>(response)
  },
  async lookup(key: string): Promise<ForecastServing> {
    const response = await fetch(`${PREDICTIONS}/lookup/${encodeURIComponent(key)}`)
    return envelopeOf<ForecastServing>(response)
  },
}

export const aiApi = {
  async chat(payload: ChatRequest): Promise<ChatResponse> {
    // ai-service fails closed: the chat endpoint requires a Keycloak bearer token.
    const token = await getValidToken()
    const response = await fetch(`${AI}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
    })
    return envelopeOf<ChatResponse>(response)
  },
}

export const analyticsApi = {
  async locale(country?: string): Promise<LocaleInfo> {
    const query = country ? `?country=${encodeURIComponent(country)}` : ''
    const response = await fetch(`${ANALYTICS}/locale${query}`)
    return envelopeOf<LocaleInfo>(response)
  },
  async overview(country?: string): Promise<AnalyticsOverview> {
    const query = country ? `?country=${encodeURIComponent(country)}` : ''
    const response = await fetch(`${ANALYTICS}/overview${query}`)
    return envelopeOf<AnalyticsOverview>(response)
  },
}

export async function fetchLocale(): Promise<LocaleInfo | null> {
  try {
    return await analyticsApi.locale()
  } catch {
    return null
  }
}

export async function fetchOverview(): Promise<AnalyticsOverview | null> {
  try {
    return await analyticsApi.overview()
  } catch {
    return null
  }
}

export async function fetchPredictionTargets(): Promise<ForecastTarget[]> {
  try {
    return await forecastsApi.targets()
  } catch {
    return []
  }
}

export async function fetchForecast(key: string): Promise<ForecastServing | null> {
  try {
    return await forecastsApi.lookup(key)
  } catch {
    return null
  }
}