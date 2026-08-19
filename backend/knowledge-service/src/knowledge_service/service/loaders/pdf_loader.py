"""PDF loader — page-aware extraction via pypdf (imported lazily)."""

from __future__ import annotations

import io
import os

from knowledge_service.configuration import KnowledgeSettings
from knowledge_service.service.loaders.base import DocumentLoader, LoadedDocument, LoaderError


class PdfLoader(DocumentLoader):
    """Extract text from a PDF (every page, up to ``pdf_max_pages``)."""

    formats = (".pdf",)
    kind = "pdf"

    def __init__(self, settings: KnowledgeSettings):
        self.settings = settings

    def load(self, raw: bytes, *, filename: str) -> list[LoadedDocument]:
        try:
            from pypdf import PdfReader
        except ImportError as err:  # pragma: no cover - optional dependency
            raise LoaderError(
                "LOADER_UNAVAILABLE", "PDF parsing requires the 'pypdf' package (pip install pypdf)"
            ) from err

        try:
            reader = PdfReader(io.BytesIO(raw))
            pages: list[str] = []
            for index, page in enumerate(reader.pages):
                if index >= self.settings.pdf_max_pages:
                    break
                pages.append(page.extract_text() or "")
        except Exception as err:  # noqa: BLE001 - pypdf raises many parse error types
            raise LoaderError("PARSE_ERROR", f"could not parse PDF: {err}") from err

        text = "\n\n".join(page for page in pages if page.strip())
        if not text:
            raise LoaderError("PARSE_ERROR", "PDF contained no extractable text (scanned? OCR required)")

        metadata_title = getattr(reader, "metadata", None)
        metadata_title = str(metadata_title.title) if metadata_title and metadata_title.title else None
        title = metadata_title or os.path.splitext(os.path.basename(filename))[0]
        return [
            LoadedDocument(
                title=title,
                doc_type="GUIDELINE",
                text=text,
                source_format="PDF",
                ingestion_ref=filename,
                metadata={"pages": len(pages), "scanned": False},
            )
        ]