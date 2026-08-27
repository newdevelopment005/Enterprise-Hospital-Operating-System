// Typed client for the ai-service (HospitalGPT) REST API.

import { AuthError, getValidToken } from './auth'
import type {
  AiModel,
  AiStatus,
  ApiEnvelope,
  ChatIn,
  ChatOut,
  Conversation,
  FeedbackIn,
  Memory,
  Message,
  OcrOut,
  Prompt,
  TranscribeOut,
  TtsOut,
} from './types'

const BASE = '/api/v1/ai'
const DEFAULT_TIMEOUT_MS = 180_000

async function authHeaders(): Promise<Record<string, string>> {
  try {
    const token = await getValidToken()
    return { Authorization: `Bearer ${token}` }
  } catch {
    throw new AuthError()
  }
}

async function parseEnvelope<T>(response: Response): Promise<ApiEnvelope<T>> {
  const text = await response.text()
  if (!text.trim()) {
    throw new Error(`Backend service unavailable (HTTP ${response.status}) — is ai-service running on port 8506?`)
  }
  try {
    return JSON.parse(text) as ApiEnvelope<T>
  } catch {
    throw new Error(`Backend returned an invalid response (HTTP ${response.status})`)
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = { 'Content-Type': 'application/json', ...(await authHeaders()), ...options.headers }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, { headers, ...options, signal: controller.signal })
  } catch (err) {
    if (controller.signal.aborted) {
      throw new Error('The request timed out. The local AI model may still be loading - please try again.')
    }
    throw err instanceof Error ? err : new Error('Network error')
  } finally {
    clearTimeout(timer)
  }
  if (response.status === 401) throw new AuthError('Session expired, please sign in again')
  const envelope = await parseEnvelope<T>(response)
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}

export const aiApi = {
  // chat
  chat(payload: ChatIn): Promise<ChatOut> {
    return request('/chat', { method: 'POST', body: JSON.stringify(payload) })
  },
  sendFeedback(payload: FeedbackIn): Promise<{ id: string }> {
    return request('/feedback', { method: 'POST', body: JSON.stringify(payload) })
  },

  // conversations
  listConversations(userId?: string): Promise<{ items: Conversation[]; total: number }> {
    const params = userId ? `?user_id=${encodeURIComponent(userId)}` : ''
    return request(`/conversations${params}`)
  },
  listMessages(conversationId: string): Promise<{ items: Message[]; total: number }> {
    return request(`/conversations/${conversationId}/messages`)
  },

  // models
  listModels(): Promise<{ items: AiModel[]; total: number }> {
    return request('/models')
  },
  loadModel(modelKey: string): Promise<AiModel> {
    return request(`/models/${encodeURIComponent(modelKey)}/load`, { method: 'POST' })
  },
  unloadModel(modelKey: string): Promise<AiModel> {
    return request(`/models/${encodeURIComponent(modelKey)}/unload`, { method: 'POST' })
  },

  // prompts & memory
  listPrompts(): Promise<{ items: Prompt[]; total: number }> {
    return request('/prompts')
  },
  listMemories(): Promise<{ items: Memory[]; total: number }> {
    return request('/memories')
  },
  addMemory(payload: { user_id: string; memory_type: string; content: string; importance?: number }): Promise<Memory> {
    return request('/memories', { method: 'PUT', body: JSON.stringify(payload) })
  },

  // media facades
  stt(audio: Blob): Promise<TranscribeOut> {
    const form = new FormData()
    form.append('audio', audio, 'clip.webm')
    return requestMedia<TranscribeOut>(`/stt`, form)
  },
  ocr(image: File): Promise<OcrOut> {
    const form = new FormData()
    form.append('image', image)
    return requestMedia<OcrOut>(`/ocr`, form)
  },
  tts(text: string): Promise<TtsOut> {
    return request('/tts', { method: 'POST', body: JSON.stringify({ text }) })
  },

  // status
  status(): Promise<AiStatus> {
    return request('/status')
  },
}

async function requestMedia<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { method: 'POST', body: form, headers: await authHeaders() })
  if (response.status === 401) throw new AuthError('Session expired, please sign in again')
  const envelope = await parseEnvelope<T>(response)
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}