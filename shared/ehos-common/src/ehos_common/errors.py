"""Exception types used across the EHOS event bus (validate, consume, retry, DLQ)."""

from __future__ import annotations

from .retry import CONSUMER_ERROR, INVALID_SCHEMA, OUT_OF_RETRIES, UNKNOWN_EVENT_TYPE, is_transient


class EventBusError(Exception):
    """A failure while producing/validating/consuming an event.

    ``code`` uses the DLQ failure taxonomy (EVENT_BUS_SCHEMAS.md §6.2).
    """

    def __init__(self, message: str, *, code: str = CONSUMER_ERROR, transient: bool | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.transient = is_transient(code) if transient is None else transient


class SchemaValidationError(EventBusError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code=INVALID_SCHEMA)


class UnknownEventTypeError(EventBusError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code=UNKNOWN_EVENT_TYPE)


class HandlerRejectedError(EventBusError):
    """A handler rejected the event as unprocessable (permanent, e.g. business rule)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="BUSINESS_REJECTED")


class OutOfRetriesError(EventBusError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code=OUT_OF_RETRIES)