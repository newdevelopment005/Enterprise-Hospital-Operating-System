// Typed client for the ai-service (HospitalGPT) REST API.

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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const envelope = (await response.json()) as ApiEnvelope<T>
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
  const response = await fetch(`${BASE}${path}`, { method: 'POST', body: form })
  const envelope = (await response.json()) as ApiEnvelope<T>
  if (!envelope.success) throw new Error(envelope.message || envelope.errorCode || 'Request failed')
  return envelope.data
}