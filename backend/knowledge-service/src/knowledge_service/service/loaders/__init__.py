"""Document loaders for the Medical Knowledge Base.

Extract structured/plain text from uploaded files into zero or more
``LoadedDocument`` objects that the ingestion pipeline chunks, embeds and maps
to ``KnowledgeDocument`` rows. Every parser is offline; optional binary-parser
libraries (pypdf, python-docx) are imported lazily.
"""

from __future__ import annotations

from knowledge_service.service.loaders.base import (
    DocumentLoader,
    LoadedDocument,
    LoaderError,
)
from knowledge_service.service.loaders.registry import get_loader, load_documents

__all__ = [
    "DocumentLoader",
    "LoadedDocument",
    "LoaderError",
    "get_loader",
    "load_documents",
]