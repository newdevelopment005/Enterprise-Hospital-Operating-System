"""Event consumption runtime: validate -> dispatch -> retry -> DLQ.

Transport-agnostic: consumers/publishers behind small protocols, so the
runtime is unit-testable with in-memory fakes and runs on aiokafka in
production. Retry state lives in the X-EHOS-* headers (EVENT_BUS_SCHEMAS.md
§5.3); each transient failure republishes the *original envelope unchanged* to
the next ``<topic>.retry.<delay>`` tier, and exhausted or permanent failures
land on ``<topic>.dlq``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from . import dlq as dlq_mod
from .errors import EventBusError
from .event_registry import EventRegistry
from .retry import (
    CONSUMER_ERROR,
    INVALID_SCHEMA,
    build_retry_headers,
    parse_retry_headers,
    retry_count_from_headers,
    sanitize_error,
)

logger = logging.getLogger("ehos.eventbus")


@dataclass
class Record:
    """Normalized transport message (topic/partition/offset/headers/value)."""

    topic: str
    value: str
    headers: list[tuple[str, str]] | None = None
    partition: int | None = None
    offset: int | None = None


class ConsumerSource(Protocol):
    """Anything async-iterable of records with a commit() (KafkaConsumer/fakes)."""

    def __aiter__(self) -> AsyncIterator[Record]: ...

    async def commit(self) -> None: ...


class PublisherSink(Protocol):
    """Anything that can publish an envelope dict (KafkaProducer/fakes)."""

    async def publish_envelope(
        self,
        topic: str,
        envelope: dict,
        headers: list[tuple[str, str]] | None = None,
    ) -> None: ...


class EventHandler(Protocol):
    async def __call__(self, envelope: dict, *, record: Record) -> None: ...


@dataclass
class ProcessOutcome:
    status: str  # consumed | retried | dlq | ignored | rejected
    dest_topic: str | None = None
    retry_count: int = 0


class EventProcessor:
    """Consumes envelopes, validates them against the registry, dispatches to
    handlers, and routes failures through the retry ladder to the DLQ."""

    def __init__(
        self,
        *,
        consumer: ConsumerSource,
        publisher: PublisherSink,
        registry: EventRegistry,
        handlers: dict[str, EventHandler],
        group_id: str,
        log: logging.Logger | None = None,
    ) -> None:
        self.consumer = consumer
        self.publisher = publisher
        self.registry = registry
        self.handlers = handlers
        self.group_id = group_id
        self.log = log or logger
        self.processed = 0
        self.failed = 0

    def topics(self) -> list[str]:
        """Topics this processor should subscribe to (main + retry tiers)."""
        return self.registry.topics_for(list(self.handlers))

    def handler_for(self, event_type: str) -> EventHandler | None:
        return self.handlers.get(event_type)

    async def run(self, *, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        self.log.info("event processor starting", extra={"group": self.group_id, "topics": self.topics()})
        while not stop.is_set():
            try:
                async for record in self.consumer:
                    outcome = await self.process_record(record)
                    self.log.debug("processed", extra={"record": record.topic, "outcome": outcome.status})
                    await self.consumer.commit()
                if getattr(self.consumer, "eof", False):
                    break
            except asyncio.CancelledError:  # pragma: no cover - shutdown path
                raise
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                self.log.exception("event processor loop error", extra={"error": sanitize_error(str(exc))})
                await asyncio.sleep(1.0)
        self.log.info(
            "event processor stopped",
            extra={"group": self.group_id, "processed": self.processed, "failed": self.failed},
        )

    async def process_record(self, record: Record) -> ProcessOutcome:
        try:
            envelope = json.loads(record.value)
        except (json.JSONDecodeError, TypeError) as exc:
            return await self._record_failure(
                record=record,
                envelope=None,
                error_code=INVALID_SCHEMA,
                error_message=f"Undecodable message body: {exc}",
            )

        retry_count = retry_count_from_headers(record.headers)
        event_type = envelope.get("eventType") if isinstance(envelope, dict) else None
        handler = self.handler_for(event_type) if event_type else None
        if handler is None:
            return ProcessOutcome(status="ignored", retry_count=retry_count)

        try:
            self.registry.validate(envelope)
            await handler(envelope, record=record)
            self.processed += 1
            return ProcessOutcome(status="consumed", retry_count=retry_count)
        except EventBusError as exc:
            self.failed += 1
            return await self._record_failure(record, envelope, exc.code, exc)
        except Exception as exc:  # noqa: BLE001 - unknown handler error is transient
            self.failed += 1
            return await self._record_failure(record, envelope, CONSUMER_ERROR, f"{type(exc).__name__}: {exc}")

    async def _record_failure(
        self,
        record: Record,
        envelope: dict | None,
        error_code: str,
        error_message: object,
    ) -> ProcessOutcome:
        envelope = envelope or {}
        retry_count = retry_count_from_headers(record.headers)
        event_type = envelope.get("eventType") or "UNKNOWN"
        base_topic = record.topic
        policy = self.registry.retry_policy(event_type) if self.registry.known(event_type) else None
        if policy is not None:
            base_topic = self.registry.topic(event_type)

        failed_attempt = retry_count + 1
        message = str(error_message)
        if policy is not None and not policy.should_dlq(failed_attempt, error_code):
            dest = policy.retry_topic(base_topic, failed_attempt)
            headers = build_retry_headers(retry_count=failed_attempt, reason=message, max_attempts=policy.max_attempts)
            await self.publisher.publish_envelope(dest, envelope, headers=headers)
            return ProcessOutcome(status="retried", dest_topic=dest, retry_count=failed_attempt)

        dest = f"{base_topic}.dlq" if policy is None else policy.dlq_topic(base_topic)
        failure = dlq_mod.build_failure_record(
            event_type=event_type,
            event_id=envelope.get("eventId", ""),
            original_envelope=envelope,
            original_topic=base_topic,
            original_partition=record.partition,
            original_offset=record.offset,
            consumed_from=record.topic,
            group_id=self.group_id,
            error_code=error_code,
            error_message=message,
            retry_count=retry_count,
        )
        await self.publisher.publish_envelope(dest, failure, headers=list(parse_retry_headers(record.headers).items()))
        return ProcessOutcome(status="dlq", dest_topic=dest, retry_count=retry_count)