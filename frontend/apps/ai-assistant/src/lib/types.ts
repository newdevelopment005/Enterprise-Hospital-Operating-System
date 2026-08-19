// Types for the ai-service (HospitalGPT) REST API.

export interface ApiEnvelope<T> {
  success: boolean
  data: T
  statusCode?: number
  message?: string
  errorCode?: string
}

export interface ChatIn {
  message: string
  conversation_id?: string
  user_id?: string
  model_key?: string
  use_rag?: boolean
}

export interface SourceRef {
  document_id: string
  document_title: string
  doc_type: string
  chunk_id: string
  score: number
}

export interface ChatOut {
  answer: string
  request_id: string
  conversation_id: string
  model_key: string
  sources: SourceRef[]
  retrieved: boolean
  tokens_in: number
  tokens_out: number
  latency_ms: number
}

export interface Conversation {
  id: string
  user_id: string
  agent_key?: string | null
  title?: string | null
  model_key?: string | null
  system_prompt_code?: string | null
  summary?: string | null
  last_message_at?: string | null
  created_at: string
}

export interface Message {
  id: string
  conversation_id: string
  role: 'USER' | 'ASSISTANT' | 'SYSTEM' | 'TOOL'
  content: string
  tokens_in?: number | null
  tokens_out?: number | null
  latency_ms?: number | null
  request_id?: string | null
  sources?: { items?: SourceRef[] } | null
  created_at: string
}

export interface AiModel {
  id: string
  model_key: string
  family: string
  base_name: string
  version: string
  quantization?: string | null
  context_window?: number | null
  purpose?: string | null
  approval_status: string
  approved_at?: string | null
  created_at: string
  load_status?: string | null
}

export interface Prompt {
  id: string
  code: string
  name: string
  purpose?: string | null
  template: string
  vars_schema?: unknown | null
  safety_rules?: unknown | null
  is_active: boolean
  version: number
  created_at: string
}

export interface Memory {
  id: string
  user_id: string
  memory_type: string
  content: string
  importance: number
  created_at: string
}

export interface AiStatus {
  service: string
  version: string
  inference_adapter: string
  embedding_adapter: string
  default_model_key: string
  tools: string[]
}

export interface FeedbackIn {
  ai_request_id: string
  user_id: string
  rating?: number
  category?: string
  comment?: string
  accepted?: boolean
}

export interface TranscribeOut {
  text: string
  engine: string
  request_id: string
}

export interface OcrOut {
  text: string
  engine: string
  request_id: string
}

export interface TtsOut {
  audio_base64: string
  mime: string
  request_id: string
}