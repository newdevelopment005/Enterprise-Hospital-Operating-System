"""Event-bus integration for the knowledge-service.

Publishes ``KnowledgeDocumentIngested`` (EVENT_BUS_SCHEMAS.md catalog ≥§4.9) on
successful ingestion via the shared EHOS producer. The producer is optional in
local dev (``app.state.producer`` may be ``None`` when Kafka is unreachable), so
every publish is best-effort and never breaks ingestion.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ehos_common import DomainEvent, EventRegistry, KafkaProducer

logger = logging.getLogger("knowledge_service.events")

_REGISTRY = EventRegistry()


def _domain_event(doc: Any) -> DomainEvent:
    payload: dict = {
        "documentId": str(doc.id),
        "docType": doc.doc_type,
        "ingestedAt": (doc.created_at or datetime.now(UTC)).isoformat(),
    }
    if doc.title:
        payload["title"] = doc.title
    return DomainEvent(
        event_type="KnowledgeDocumentIngested",
        source="knowledge-service",
        payload=payload,
    )


async def publish_ingested(producer: KafkaProducer | None, documents: list[Any], outbox=None) -> int:
    """Publish one ``KnowledgeDocumentIngested`` per ingested document.

    Returns the number of documents whose event was staged/published. Events are
    staged on the request outbox (published after the transaction commits) when
    one is wired; otherwise they are published immediately. Each publish is
    validated against the registry so a contract break surfaces as a logged
    warning, never a crash.
    """
    if producer is None:
        return 0
    published = 0
    topic = _REGISTRY.topic("KnowledgeDocumentIngested")
    for doc in documents:
        event = _domain_event(doc)
        try:
            _REGISTRY.validate(event.envelope())
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await producer.publish(topic, event)
            published += 1
        except Exception:  # noqa: BLE001 - best-effort eventing
            logger.exception(
                "failed to publish KnowledgeDocumentIngested", extra={"document": str(getattr(doc, "id", None))}
            )
    return published