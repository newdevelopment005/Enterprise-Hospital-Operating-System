"""Event envelope and Kafka producer.

Event envelope per EVENT_BUS.md / TECH_STACK.md:

    {
      "eventId": "...",
      "eventType": "...",
      "eventVersion": "1",
      "timestamp": "...",
      "source": "...",
      "correlationId": "...",
      "userId": "...",
      "payload": {...}
    }

Events are immutable, versioned, and documented.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .worker import Record


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    payload: dict
    source: str
    event_version: str = "1"
    correlation_id: str | None = None
    user_id: str | None = None

    def envelope(self) -> dict:
        return {
            "eventId": str(uuid.uuid4()),
            "eventType": self.event_type,
            "eventVersion": self.event_version,
            "timestamp": datetime.now(UTC).isoformat(),
            "source": self.source,
            "correlationId": self.correlation_id,
            "userId": self.user_id,
            "payload": self.payload,
        }


class KafkaProducer:
    """Thin async wrapper around aiokafka, safe to start/stop with the app."""

    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    @property
    def connected(self) -> bool:
        return self._producer is not None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            acks="all",
            retries=5,
            enable_idempotence=True,
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, event: DomainEvent, headers: list[tuple[str, str]] | None = None) -> None:
        await self.publish_envelope(topic, event.envelope(), headers=headers)

    async def publish_envelope(self, topic: str, envelope: dict, headers: list[tuple[str, str]] | None = None) -> None:
        """Publish a raw envelope dict (used by the EventProcessor retry/DLQ paths)."""
        if self._producer is None:
            raise RuntimeError("Producer not started")
        raw_headers = [(key, value.encode("utf-8")) for key, value in headers or []]
        await self._producer.send_and_wait(topic, json.dumps(envelope).encode("utf-8"), headers=raw_headers)


class KafkaConsumer:
    """Thin async wrapper around an aiokafka consumer (manual commit, earliest)."""

    def __init__(
        self,
        *,
        topics: list[str],
        group_id: str,
        bootstrap_servers: str,
        auto_offset_reset: str = "earliest",
    ):
        self.topics = topics
        self.group_id = group_id
        self._consumer = AIOKafkaConsumer(
            *topics,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=False,
        )

    async def start(self) -> None:
        await self._consumer.start()

    async def stop(self) -> None:
        await self._consumer.stop()

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        """Yield normalized Records (decode value/headers from bytes to text)."""
        async for message in self._consumer:
            value = message.value or ""
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            headers = [
                (key, val.decode("utf-8", errors="replace") if isinstance(val, bytes) else str(val))
                for key, val in message.headers or []
            ]
            yield Record(
                topic=message.topic,
                value=value,
                headers=headers,
                partition=message.partition,
                offset=message.offset,
            )

    async def commit(self) -> None:
        await self._consumer.commit()
