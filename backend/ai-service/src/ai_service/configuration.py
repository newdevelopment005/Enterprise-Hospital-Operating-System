"""Application settings for the ai-service (HospitalGPT).

Extends the shared ``ServiceSettings`` with the AI runtime addressing:
all model traffic stays on localhost (Ollama / llama.cpp); the adapter switch
guarantees no external calls. STT/TTS/OCR facade settings included.
"""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class AiSettings(ServiceSettings):
    """AI Gateway / HospitalGPT settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- runtime binding (offline / OpenAI-compatible) ---
    inference_adapter: str = "mock"  # mock | ollama | llamacpp | openai
    embedding_adapter: str = "mock"  # mock | ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    ollama_embedding_model: str = "nomic-embed-text"
    llamacpp_base_url: str = "http://localhost:8080"

    # OpenAI-compatible endpoint (vLLM / LM Studio / OpenAI). The API key is
    # optional: many self-hosted compatible servers run keyless on localhost.
    openai_base_url: str = "http://localhost:8000/v1"
    openai_api_key: str | None = None
    openai_model: str = "ehos-gpt"

    # --- knowledge service (RAG bridge) ---
    knowledge_service_url: str = "http://localhost:8505"
    knowledge_timeout: float = 20.0
    rag_top_k: int = 5

    # --- defaults ---
    default_model_key: str = "llama-3.1-8b"
    default_system_prompt_code: str = "hospitalgpt_system"
    max_context_windows: int = 24

    # --- media facades ---
    stt_adapter: str = "mock"  # mock | http
    tts_adapter: str = "mock"  # mock | http
    ocr_adapter: str = "mock"  # mock | http
    stt_http_url: str | None = None
    stt_http_token: str | None = None
    tts_http_url: str | None = None
    tts_http_token: str | None = None
    ocr_http_url: str | None = None
    ocr_http_token: str | None = None
    media_timeout: float = 60.0


@lru_cache
def get_settings() -> AiSettings:
    """Build (and cache) the ai-service settings."""
    settings = AiSettings()  # type: ignore[call-arg]
    settings.service_name = "ai-service"
    settings.database_name = "ehos_ai"
    return settings