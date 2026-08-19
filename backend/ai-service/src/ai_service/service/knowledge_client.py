"""Knowledge-service client (RAG bridge) for the ai-service.

All calls target the local knowledge-service only (offline). If the knowledge
service is unreachable, retrieval is safely skipped and the chat still answers
with a "cannot verify" refusal.
"""

from __future__ import annotations

import httpx

from ai_service.configuration import AiSettings
from ai_service.dto import schemas as dto


class KnowledgeClient:
    """Thin async client for the knowledge-service search endpoint."""

    def __init__(self, settings: AiSettings):
        self.settings = settings
        self.base_url = settings.knowledge_service_url

    async def search(self, query: str, top_k: int | None = None, user_id: str | None = None) -> list[dto.SourceRef]:
        url = self.base_url.rstrip("/") + "/api/v1/knowledge/search"
        payload = {"query": query, "top_k": (top_k or self.settings.rag_top_k), "user_id": user_id}
        try:
            async with httpx.AsyncClient(timeout=self.settings.knowledge_timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError:
            return []
        hits = (body.get("data") or {}).get("hits") or []
        return [
            dto.SourceRef(
                document_id=h["document_id"],
                document_title=h["document_title"],
                doc_type=h["doc_type"],
                chunk_id=h["chunk_id"],
                score=float(h.get("score", 0.0)),
            )
            for h in hits
        ]

    def render_context(self, sources: list[dto.SourceRef]) -> str:
        """Compose the retrieval context block lines used in the prompt."""
        return "\n".join(f"[{s.doc_type}] {s.document_title}: {s.document_id}" for s in sources)