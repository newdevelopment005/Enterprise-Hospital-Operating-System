"""Pydantic DTOs for the ai-service REST API.

Field names snake_case matching the DDL and V002 default system prompt.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

FAMILIES = ("LLM", "EMBEDDING", "ASR", "TTS", "OCR", "VISION", "PREDICTION", "AGENT")
REQUEST_TYPES = ("CHAT", "SUMMARIZE", "ANALYZE", "SEARCH", "DOCUMENT", "TRANSCRIBE", "OCR", "PREDICT", "AGENT")
APPROVAL_LEVELS = (1, 2, 3, 4)
MEMORY_TYPES = ("EPISODIC", "FACT", "WORKFLOW", "PREFERENCE", "KNOWLEDGE")


# --- chat -----------------------------------------------------------------------


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    user_id: str | None = Field(default=None, min_length=1)
    model_key: str | None = None
    use_rag: bool = True
    request_type: str = Field(default="CHAT", pattern=f"^({'|'.join(REQUEST_TYPES)})$")


class SourceRef(BaseModel):
    document_id: str
    document_title: str
    doc_type: str
    chunk_id: str
    score: float


class ChatOut(BaseModel):
    answer: str
    request_id: str
    conversation_id: str
    model_key: str
    sources: list[SourceRef] = Field(default_factory=list)
    retrieved: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0


# --- conversations ---------------------------------------------------------------


class ConversationIn(BaseModel):
    user_id: str = Field(min_length=1)
    agent_key: str | None = None
    title: str | None = Field(default=None, max_length=255)
    model_key: str | None = None
    system_prompt_code: str | None = None


class ConversationOut(BaseModel):
    id: str
    user_id: str
    agent_key: str | None
    title: str | None
    model_key: str | None
    system_prompt_code: str | None
    summary: str | None
    last_message_at: datetime | None
    created_at: datetime


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int | None
    request_id: str | None
    sources: dict | None
    created_at: datetime


# --- models ----------------------------------------------------------------------


class ModelRegisterIn(BaseModel):
    model_key: str = Field(min_length=1, max_length=255)
    family: str = Field(pattern=f"^({'|'.join(FAMILIES)})$")
    base_name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=100)
    quantization: str | None = None
    context_window: int | None = Field(default=None, ge=1024)
    purpose: str | None = None
    artifact_ref: str | None = None
    approved: bool = False


class ModelOut(BaseModel):
    id: str
    model_key: str
    family: str
    base_name: str
    version: str
    quantization: str | None
    context_window: int | None
    purpose: str | None
    approval_status: str
    approved_at: datetime | None
    created_at: datetime
    load_status: str | None = None


# --- prompts ---------------------------------------------------------------------


class PromptIn(BaseModel):
    code: str = Field(min_length=1, max_length=100, pattern="^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=255)
    purpose: str | None = None
    template: str = Field(min_length=1, max_length=50_000)
    vars_schema: dict | None = None
    safety_rules: dict | None = None
    is_active: bool = True


class PromptOut(BaseModel):
    id: str
    code: str
    name: str
    purpose: str | None
    template: str
    vars_schema: dict | None
    safety_rules: dict | None
    is_active: bool
    version: int
    created_at: datetime


# --- memory ----------------------------------------------------------------------


class MemoryIn(BaseModel):
    user_id: str = Field(min_length=1)
    memory_type: str = Field(pattern=f"^({'|'.join(MEMORY_TYPES)})$")
    content: str = Field(min_length=1, max_length=50_000)
    importance: int = Field(default=1, ge=1, le=5)


class MemoryOut(BaseModel):
    id: str
    user_id: str
    memory_type: str
    content: str
    importance: int
    created_at: datetime


# --- approval --------------------------------------------------------------------


class ApprovalDecisionIn(BaseModel):
    approver_id: str = Field(min_length=1)
    approved: bool
    comments: str | None = None


# --- feedback --------------------------------------------------------------------


class FeedbackIn(BaseModel):
    ai_request_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    rating: int | None = Field(default=None, ge=1, le=5)
    category: str | None = None
    comment: str | None = None
    accepted: bool | None = None


# --- media facades ---------------------------------------------------------------


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: str | None = None


class TtsOut(BaseModel):
    audio_base64: str
    mime: str = "audio/wav"


class TranscribeOut(BaseModel):
    text: str
    engine: str
    request_id: str


class OcrOut(BaseModel):
    text: str
    engine: str
    request_id: str


# --- agents ----------------------------------------------------------------------


class AgentRunIn(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(min_length=1)
    context: dict | None = None


class AgentActionDecisionIn(BaseModel):
    approver_id: str = Field(min_length=1)
    approved: bool
    comments: str | None = None


class StatusOut(BaseModel):
    service: str
    version: str
    inference_adapter: str
    embedding_adapter: str
    default_model_key: str
    tools: list[str] = Field(default_factory=list)