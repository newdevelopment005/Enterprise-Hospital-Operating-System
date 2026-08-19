"""Kafka consumer that turns domain events into notifications.

Subscribes to the topics that EHOS producers actually write (the registry
catalog topics) and dispatches configured notifications via the notification
service. The shared :class:`EventProcessor` provides schema validation, the
retry ladder and the DLQ on transient/permanent failures. Idempotency is
delegated to the processor's header-based retry tracking plus the DB-level
``notification_id`` uniqueness the service enforces (see
:meth:`NotificationService.create_and_send`).

The old loop subscribed to ``appointment.topic`` — a topic no producer writes —
so the pipeline never fired. It now derives topics from the event registry.
"""

import logging

from ehos_common import EventProcessor, EventRegistry, KafkaConsumer, KafkaProducer

from notification_service.service.notification_service import NotificationService

log = logging.getLogger("notification-service")

# Any extra topics that registered producers write but that have no registry
# entry yet (legacy or pre-migration producers). Keep empty unless needed.
EXTRA_TOPICS: tuple[str, ...] = ()


class NotificationEventProcessor:
    """Wraps the shared EventProcessor, configured for notification routing."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        service: NotificationService,
        session_factory,
        event_routing: dict[str, dict],
        producer: KafkaProducer,
        consumer=None,
    ):
        self.service = service
        self.session_factory = session_factory
        self.event_routing = event_routing

        registry = EventRegistry()
        handlers = {
            event_type: self._make_handler(event_type, routing)
            for event_type, routing in event_routing.items()
            if registry.known(event_type)
        }
        topics = list(dict.fromkeys(registry.topics_for(list(handlers)) + list(EXTRA_TOPICS)))

        self.consumer = consumer or KafkaConsumer(
            topics=topics,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
        )
        self.processor = EventProcessor(
            consumer=self.consumer,
            publisher=producer,
            registry=registry,
            handlers=handlers,
            group_id=group_id,
            log=log,
        )

    def _make_handler(self, event_type: str, routing: dict):
        async def handler(envelope: dict, **_: object) -> None:
            payload = envelope.get("payload", {})
            recipient = payload.get("recipient") or routing.get("defaultRecipient")
            if recipient is None:
                return
            data = routing["create"](payload)
            event_id = envelope.get("eventId")
            if event_id:
                data = data.model_copy(update={"notification_id": event_id})
            async with self.session_factory() as session:
                await self.service.create_and_send(
                    session,
                    data,
                    source=envelope.get("source"),
                    correlation_id=envelope.get("correlationId"),
                )
                await session.commit()

        return handler

    async def run(self, *, stop=None) -> None:
        await self.consumer.start()
        try:
            await self.processor.run(stop=stop)
        finally:
            await self.consumer.stop()

    def stop(self) -> None:
        self.processor.log.info("notification processor stopping")