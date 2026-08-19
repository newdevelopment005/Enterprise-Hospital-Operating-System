// Typed clients for the prediction-service and ai-service REST APIs.
//
// Both are optional at runtime: the dashboard degrades to demo data when a
// service is unavailable, so every request here is wrapped in try/catch.

import type {
  ApiEnvelope,
  ChatRequest,
  ChatResponse,
  ForecastServing,
  ForecastTarget,
} from './types'

const PREDICTIONS = '/api/v1/predictions'
const AI = '/api/v1/ai'

async function envelopeOf<T>(response: Response): Promise<T> {
  const body: ApiEnvelope<T> = (await response.json()) as ApiEnvelope<T>
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
    const response = await fetch(`${AI}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return envelopeOf<ChatResponse>(response)
  },
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