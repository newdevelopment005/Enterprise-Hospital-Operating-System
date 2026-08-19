"""Structured logging per CODING_STANDARDS.md section 14.

Required fields on every log line: ``timestamp``, ``service``, ``userId``
(user when available), ``requestId``, ``operation``, ``result``, ``duration``.

Never log: passwords, medical secrets, authentication tokens, full patient records.
"""

import logging
import sys
import time

import structlog

from ehos_common.config import ServiceSettings


def configure_logging(settings: ServiceSettings) -> structlog.BoundLogger:
    logging.basicConfig(stream=sys.stdout, level=settings.log_level.upper())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("aiokafka").setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, settings.log_level.upper())),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    log: structlog.BoundLogger = structlog.get_logger(settings.service_name)
    log.msg(
        "service_started",
        service=settings.service_name,
        version=settings.service_version,
        environment=settings.environment,
    )
    return log


def bind_request(
    log: structlog.BoundLogger, *, request_id: str, user_id: str | None, operation: str
) -> structlog.BoundLogger:
    """Bind correlation context for the duration of a request."""
    return log.bind(requestId=request_id, userId=user_id, operation=operation)


def elapsed(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)