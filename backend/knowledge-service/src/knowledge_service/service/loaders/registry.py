"""Loader registry: extension/kind -> loader, autodetection, convenience API."""

from __future__ import annotations

import os

from knowledge_service.configuration import KnowledgeSettings
from knowledge_service.service.loaders.base import DocumentLoader, LoadedDocument, LoaderError
from knowledge_service.service.loaders.book_loader import BookLoader
from knowledge_service.service.loaders.formulary_loader import FormularyLoader
from knowledge_service.service.loaders.journal_loader import JournalLoader
from knowledge_service.service.loaders.pdf_loader import PdfLoader
from knowledge_service.service.loaders.sop_loader import SopLoader
from knowledge_service.service.loaders.text_loader import MarkdownLoader, TextLoader
from knowledge_service.service.loaders.word_loader import WordLoader

#: document types that imply the formula/structured drug loader
_FORMULARY_DOC_TYPES = {"FORMULARY", "MEDICATION"}


def build_loaders(settings: KnowledgeSettings) -> dict[str, DocumentLoader]:
    """Instantiate every loader bound to the service settings, keyed by kind."""
    loaders = [
        PdfLoader(settings),
        WordLoader(),
        SopLoader(),
        FormularyLoader(),
        BookLoader(),
        JournalLoader(),
        TextLoader(),
        MarkdownLoader(),
    ]
    return {loader.kind: loader for loader in loaders}


def get_loader(
    filename: str,
    *,
    kind: str | None = None,
    doc_type: str | None = None,
    settings: KnowledgeSettings,
) -> DocumentLoader:
    """Resolve a loader by explicit kind, then by file extension.

    Raises ``LoaderError(UNSUPPORTED_FORMAT)`` when no loader can be resolved.
    """
    by_kind = build_loaders(settings)
    lower_name = filename.lower()

    if kind:
        try:
            return by_kind[kind]
        except KeyError as err:
            raise LoaderError("UNSUPPORTED_FORMAT", f"unknown loader kind '{kind}'") from err

    for candidate in by_kind.values():
        if lower_name.endswith(candidate.formats):
            return candidate

    if lower_name.endswith((".json",)) and doc_type in _FORMULARY_DOC_TYPES:
        return by_kind["formulary"]

    raise LoaderError(
        "UNSUPPORTED_FORMAT",
        "no loader for this file type; specify 'kind' (sop|formulary|book|journal) for JSON files",
    )


def load_documents(
    raw: bytes,
    *,
    filename: str,
    kind: str | None = None,
    doc_type: str | None = None,
    settings: KnowledgeSettings,
) -> list[LoadedDocument]:
    """Extract documents from raw bytes using the resolved loader."""
    loader = get_loader(filename, kind=kind, doc_type=doc_type, settings=settings)
    return loader.load(raw, filename=os.path.basename(filename))