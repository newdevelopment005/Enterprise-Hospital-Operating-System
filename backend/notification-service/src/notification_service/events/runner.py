"""Background task supervision for the notification consumer."""

import asyncio
import logging
from contextlib import suppress

from notification_service.events.consumer import NotificationEventProcessor

log = logging.getLogger("notification-service")


class ConsumerRunner:
    def __init__(self, consumer: NotificationEventProcessor):
        self.consumer = consumer
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self.consumer.run(), name="notification-consumer")
        log.info("notification_consumer_started")

    async def stop(self) -> None:
        self.consumer.stop()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task