"""Tests for PredictionGenerated event publishing (best-effort, validates schema)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ehos_common import EventRegistry

from prediction_service.service.provider import publish_generated


class FakeProducer:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish_envelope(self, topic: str, envelope: dict) -> None:
        self.published.append((topic, envelope))


def _outcome() -> dict:
    return {
        "prediction_key": "ward.A.7d",
        "entity_type": "ward",
        "entity_id": str(uuid.uuid4()),
        "horizon": "7d",
        "window_from": "2026-08-18",
        "window_to": "2026-08-24",
        "forecast": {"value": [10.0, 11.0, 10.5, 11.5, 10.0, 11.0, 10.5]},
        "confidence": 0.9,
        "model_version": "v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": ["feature:ward.A.7d:history"],
    }


def test_publishes_valid_prediction_generated_event():
    producer = FakeProducer()
    asyncio_run(publish_generated(producer, _outcome()))
    assert len(producer.published) == 1
    topic, envelope = producer.published[0]
    assert topic == "ai.prediction.generated"
    assert envelope["eventType"] == "PredictionGenerated"
    payload = envelope["payload"]
    assert payload["predictionKey"] == "ward.A.7d"
    assert payload["entityType"] == "ward"
    EventRegistry().validate(envelope)


def test_publish_never_raises_on_failure():
    class BrokenProducer:
        async def publish_envelope(self, *_args):
            raise RuntimeError("kafka down")

    asyncio_run(publish_generated(BrokenProducer(), _outcome()))


def asyncio_run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)