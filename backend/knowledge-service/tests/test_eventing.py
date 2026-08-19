"""Unit tests for the knowledge-service eventing bridge."""

from __future__ import annotations

import uuid

from ehos_common import EventRegistry

from knowledge_service.entity.models import KnowledgeDocument
from knowledge_service.service.eventing import publish_ingested


class StubProducer:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    async def publish(self, topic: str, event, headers: list[tuple[str, str]] | None = None) -> None:
        self.published.append((topic, event))


def _doc(doc_type: str = "GUIDELINE", title: str = "Hand Hygiene SOP") -> KnowledgeDocument:
    return KnowledgeDocument(id=uuid.uuid4(), doc_type=doc_type, title=title, version=1)


async def test_publish_ingested_no_producer_is_noop():
    assert await publish_ingested(None, [_doc()]) == 0


async def test_publish_ingested_publishes_valid_envelopes():
    producer = StubProducer()
    docs = [_doc("GUIDELINE"), _doc("POLICY")]
    count = await publish_ingested(producer, docs)
    assert count == 2
    assert len(producer.published) == 2
    registry = EventRegistry()
    for topic, event in producer.published:
        assert topic == "knowledge.document.ingested"
        registry.validate(event.envelope())


async def test_publish_ingested_drops_non_contract_doc_types():
    """A document type outside the contract enum is not emitted (best-effort)."""
    producer = StubProducer()
    count = await publish_ingested(producer, [_doc("UNKNOWN_LEGACY")])
    assert count == 0
    assert producer.published == []