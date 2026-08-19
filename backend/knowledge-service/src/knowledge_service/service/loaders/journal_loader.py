"""Medical journal loader — structured JSON issue split into per-article docs."""

from __future__ import annotations

import json
import os

from knowledge_service.service.loaders.base import DocumentLoader, LoadedDocument, LoaderError


class JournalLoader(DocumentLoader):
    """Parse a journal issue JSON payload; one ``LoadedDocument`` per article.

    Payload shape:
        {"journal_name": "...", "volume": "12", "issue": "3",
         "articles": [{"title": "...", "doi": "...", "authors": ["..."],
                       "keywords": ["..."], "abstract": "...", "body": "..."}]}
    """

    formats = (".journal.json",)
    kind = "journal"

    def load(self, raw: bytes, *, filename: str) -> list[LoadedDocument]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as err:
            raise LoaderError("PARSE_ERROR", f"journal JSON is invalid: {err}") from err
        if not isinstance(payload, dict):
            raise LoaderError("PARSE_ERROR", "journal payload must be a JSON object")

        journal = str(payload.get("journal_name") or os.path.splitext(os.path.basename(filename))[0])
        volume = payload.get("volume")
        issue = payload.get("issue")
        articles = payload.get("articles") or []
        if not isinstance(articles, list) or not articles:
            raise LoaderError("PARSE_ERROR", "journal payload has no articles")

        documents: list[LoadedDocument] = []
        for article in articles:
            article_title = str(article.get("title") or "Untitled article")
            authors = ", ".join(article.get("authors") or [])
            keywords = article.get("keywords") or []
            abstract = str(article.get("abstract") or "")
            body = str(article.get("body") or "")
            header = (
                f"{article_title}\n"
                f"Journal: {journal} | Volume: {volume} | Issue: {issue}\n"
                f"Authors: {authors}\nKeywords: {', '.join(keywords)}\n"
            )
            text = f"{header}\nAbstract: {abstract}\n\n{body}".strip()
            documents.append(
                LoadedDocument(
                    title=article_title,
                    doc_type="JOURNAL",
                    text=text,
                    source_format="JOURNAL",
                    ingestion_ref=filename,
                    metadata={
                        "journal": journal,
                        "volume": volume,
                        "issue": issue,
                        "doi": article.get("doi"),
                        "authors": article.get("authors") or [],
                        "keywords": article.get("keywords") or [],
                    },
                )
            )
        return documents