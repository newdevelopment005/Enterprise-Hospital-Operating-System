"""EHOS shared library - cross-cutting concerns for all backend services."""

__version__ = "0.1.0"

from .api import NotFoundError, ServiceError, register_exception_handlers, success_response
from .config import ServiceSettings, get_settings
from .dlq import build_failure_record, failure_kind
from .errors import EventBusError, HandlerRejectedError, OutOfRetriesError, SchemaValidationError, UnknownEventTypeError
from .event_registry import EventRegistry
from .events import DomainEvent, KafkaConsumer, KafkaProducer
from .idempotency import IdempotencyMiddleware, default_store, fingerprint
from .outbox import Outbox
from .retry import RetryPolicy, build_retry_headers, is_permanent, is_transient
from .worker import EventProcessor, ProcessOutcome, Record

__all__ = [
    "build_failure_record",
    "build_retry_headers",
    "default_store",
    "DomainEvent",
    "EventBusError",
    "EventProcessor",
    "EventRegistry",
    "failure_kind",
    "fingerprint",
    "get_settings",
    "HandlerRejectedError",
    "IdempotencyMiddleware",
    "is_permanent",
    "is_transient",
    "KafkaConsumer",
    "KafkaProducer",
    "NotFoundError",
    "Outbox",
    "OutOfRetriesError",
    "ProcessOutcome",
    "Record",
    "RetryPolicy",
    "register_exception_handlers",
    "SchemaValidationError",
    "ServiceError",
    "ServiceSettings",
    "success_response",
    "UnknownEventTypeError",
]