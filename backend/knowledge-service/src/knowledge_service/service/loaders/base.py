"""Loader contract and shared helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LoaderError(Exception):
    """Raised when a file cannot be extracted into LoadedDocuments.

    ``code`` is a stable machine-readable error kind for the API layer:
    UNSUPPORTED_FORMAT, LOADER_UNAVAILABLE, PARSE_ERROR, PAYLOAD_LIMIT.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LoadedDocument:
    """A normalized document ready for chunking + embedding."""

    title: str
    doc_type: str
    text: str
    source_format: str
    ingestion_ref: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise LoaderError("PARSE_ERROR", "loader produced empty content")


class DocumentLoader(ABC):
    """Base class for file-format loaders."""

    #: file extensions handled, lower-case with leading dot, e.g. (".pdf",)
    formats: tuple[str, ...] = ()
    #: stable loader kind used for explicit selection, e.g. "pdf"
    kind: str = ""

    def supports(self, filename: str) -> bool:
        return filename.lower().endswith(self.formats)

    @abstractmethod
    def load(self, raw: bytes, *, filename: str) -> list[LoadedDocument]:
        """Extract documents from raw file bytes. CPU-bound; run off the loop."""