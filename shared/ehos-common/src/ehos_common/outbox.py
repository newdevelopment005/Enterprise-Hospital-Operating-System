"""Per-request in-memory outbox (transactional outbox, in-memory variant).

Services stage events on the request's SQLAlchemy session via the outbox and
publish them only after the transaction commits. This prevents phantom events:
if the DB commit fails, the staged events are discarded instead of being
delivered for a write that never happened. The ``get_session`` dependency wires
the outbox onto ``session.info``, flushes it after commit and discards it on
rollback (see backend services' ``api/routes.py``).

The outbox is per-request (owned by the session), so concurrent requests cannot
leak each other's events. Publishing remains best-effort: ``flush`` logs and
swallows producer errors so a broker outage never turns a committed write into
an error response.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger("ehos-common.outbox")

_PublishCall = Callable[[object], Awaitable[None]]


class Outbox:
    """Stages ``(publish-callable, topic, event)`` entries until the txn commits."""

    def __init__(self) -> None:
        self._entries: list[_PublishCall] = []

    def add(self, topic: str, event: object) -> None:
        """Stage an event to be published with ``producer.publish(topic, event)``."""
        self._entries.append(lambda producer: producer.publish(topic, event))

    def add_envelope(self, topic: str, envelope: dict) -> None:
        """Stage an envelope to be published with ``producer.publish_envelope``."""
        self._entries.append(lambda producer: producer.publish_envelope(topic, envelope))

    async def flush(self, producer) -> None:
        """Publish every staged entry (best-effort), then clear the queue."""
        for publish in self._entries:
            try:
                await publish(producer)
            except Exception:  # noqa: BLE001 - eventing must never break the request
                log.exception("outbox publish failed")
        self._entries.clear()

    def discard(self) -> None:
        """Drop staged entries (the transaction rolled back)."""
        self._entries.clear()

    @property
    def pending(self) -> int:
        return len(self._entries)