"""Medical book loader — structured JSON books split into per-chapter documents."""

from __future__ import annotations

import json
import os

from knowledge_service.service.loaders.base import DocumentLoader, LoadedDocument, LoaderError


class BookLoader(DocumentLoader):
    """Parse a medical book JSON payload; one ``LoadedDocument`` per chapter.

    Payload shape:
        {"title": "...", "author": "...", "edition": "3",
         "chapters": [{"number": 1, "title": "...", "content": "..."}]}
    """

    formats = (".book.json",)
    kind = "book"

    def load(self, raw: bytes, *, filename: str) -> list[LoadedDocument]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as err:
            raise LoaderError("PARSE_ERROR", f"book JSON is invalid: {err}") from err
        if not isinstance(payload, dict):
            raise LoaderError("PARSE_ERROR", "book payload must be a JSON object")

        title = str(payload.get("title") or os.path.splitext(os.path.basename(filename))[0])
        author = str(payload.get("author") or "")
        edition = payload.get("edition")
        chapters = payload.get("chapters") or []

        if not isinstance(chapters, list) or not chapters:
            flat = str(payload.get("content") or "")
            if not flat.strip():
                raise LoaderError("PARSE_ERROR", "book payload has no chapters or content")
            return [
                LoadedDocument(
                    title=title,
                    doc_type="TEXTBOOK",
                    text=flat,
                    source_format="TEXTBOOK",
                    ingestion_ref=filename,
                    metadata={"author": author, "edition": edition},
                )
            ]

        documents: list[LoadedDocument] = []
        for chapter in chapters:
            chapter_number = chapter.get("number")
            chapter_title = str(chapter.get("title") or f"Chapter {chapter_number}")
            content = str(chapter.get("content") or "")
            documents.append(
                LoadedDocument(
                    title=f"{title} — {chapter_title}",
                    doc_type="TEXTBOOK",
                    text=content,
                    source_format="TEXTBOOK",
                    ingestion_ref=filename,
                    metadata={"book": title, "author": author, "edition": edition, "chapter": chapter_number},
                )
            )
        return documents