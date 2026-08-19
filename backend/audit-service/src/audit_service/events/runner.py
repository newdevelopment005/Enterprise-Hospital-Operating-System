"""Kafka consumer for the audit-service.

Starts the consumer in an asyncio task as part of the application lifespan.
"""

import asyncio
import logging
from contextlib import suppress

from audit_service.events.consumer import AuditConsumer

log = logging.getLogger("audit-service")


class ConsumerRunner:
    def __init__(self, consumer: AuditConsumer):
        self.consumer = consumer
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self.consumer.run(), name="audit-consumer")

    async def stop(self) -> None:
        self.consumer.stop()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task