"""Plain-text and Markdown loaders (fallback for guidelines/policies, etc.)."""

from __future__ import annotations

import os

from knowledge_service.service.loaders.base import DocumentLoader, LoadedDocument


class TextLoader(DocumentLoader):
    """Whole-file text loader (.txt)."""

    formats = (".txt",)
    kind = "text"

    def load(self, raw: bytes, *, filename: str) -> list[LoadedDocument]:
        text = raw.decode("utf-8", errors="replace")
        title = f"{os.path.splitext(os.path.basename(filename))[0]}: {text.splitlines()[0][:120]}" if text else filename
        return [
            LoadedDocument(
                title=title,
                doc_type="GUIDELINE",
                text=text,
                source_format="TEXT",
                ingestion_ref=filename,
            )
        ]


class MarkdownLoader(DocumentLoader):
    """Whole-file Markdown loader (.md / .markdown)."""

    formats = (".md", ".markdown")
    kind = "markdown"

    def load(self, raw: bytes, *, filename: str) -> list[LoadedDocument]:
        text = raw.decode("utf-8", errors="replace")
        title = _first_heading(text) or os.path.splitext(os.path.basename(filename))[0]
        return [
            LoadedDocument(
                title=title,
                doc_type="GUIDELINE",
                text=text,
                source_format="MARKDOWN",
                ingestion_ref=filename,
            )
        ]


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or None
    return None