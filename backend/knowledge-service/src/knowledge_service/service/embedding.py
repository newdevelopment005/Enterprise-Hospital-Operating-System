"""Embedding engine for the knowledge-service.

Pluggable offline adapters:
- `mock`: deterministic hash-based embeddings, no network (tests/dev).
- `ollama`: calls the local Ollama embeddings endpoint (offline LAN only).

Selection via settings.embedding_adapter. Never calls external services.
"""

from __future__ import annotations

import hashlib
import math
import re
import urllib.parse

import httpx

from knowledge_service.configuration import KnowledgeSettings


class EmbeddingError(Exception):
    """Raised when the configured local embedding engine cannot embed."""


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class EmbeddingEngine:
    """Factory selecting the embedding adapter from settings."""

    def __init__(self, settings: KnowledgeSettings):
        self.settings = settings
        if settings.embedding_adapter == "ollama":
            self._impl = _OllamaEmbedder(settings)
        else:
            self._impl = _MockEmbedder(settings)

    @property
    def model(self) -> str:
        return self._impl.model

    @property
    def dimensions(self) -> int:
        return self._impl.dimensions

    async def embed(self, text: str) -> list[float]:
        return await self._impl.embed(text)


class _MockEmbedder:
    """Deterministic, dependency-free embeddings for offline tests/dev."""

    def __init__(self, settings: KnowledgeSettings):
        self._settings = settings
        self.model = "mock-embed-v1"
        self.dimensions = 256

    async def embed(self, text: str) -> list[float]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        vector = [0.0] * self.dimensions
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % self.dimensions
            vector[index] += 1.0
        return _normalize(vector)


class _OllamaEmbedder:
    """Embeds via the local Ollama server (offline)."""

    def __init__(self, settings: KnowledgeSettings):
        self._settings = settings
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dim

    async def embed(self, text: str) -> list[float]:
        url = urllib.parse.urljoin(self._settings.ollama_base_url.rstrip("/") + "/", "api/embeddings")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json={"model": self.model, "prompt": text})
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as err:
            raise EmbeddingError(f"local Ollama embedding runtime unavailable: {err}") from err
        embedding = payload.get("embedding")
        if not embedding:
            raise EmbeddingError("local Ollama embedding runtime returned no vector")
        embedding = [float(v) for v in embedding]
        if self.dimensions == 0:
            self.dimensions = len(embedding)
        return _normalize(embedding)