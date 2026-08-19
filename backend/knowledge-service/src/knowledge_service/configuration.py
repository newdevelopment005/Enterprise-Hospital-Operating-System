"""Application settings for the knowledge-service.

Pickup the shared ``ServiceSettings`` (database_url, env vars) plus
RAG-specific defaults: chunking, embeddings and retrieval tuning.
"""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class KnowledgeSettings(ServiceSettings):
    """Knowledge-service (RAG) settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- RAG chunking ---
    chunk_size: int = 800
    chunk_overlap: int = 120

    # --- Embedding engine ---
    embedding_adapter: str = "mock"  # mock | ollama
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 384

    # --- Retrieval ---
    search_top_k: int = 8
    search_max_top_k: int = 25
    similarity_threshold: float = 0.1

    # --- Ingestion (document loaders) ---
    max_upload_bytes: int = 20_000_000
    pdf_max_pages: int = 500
    max_documents_per_file: int = 2000


@lru_cache
def get_settings() -> KnowledgeSettings:
    """Build (and cache) the knowledge-service settings."""
    settings = KnowledgeSettings()  # type: ignore[call-arg]
    settings.service_name = "knowledge-service"
    settings.database_name = "ehos_knowledge"
    return settings