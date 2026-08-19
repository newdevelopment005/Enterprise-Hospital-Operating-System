"""DLQ failure envelope builder (EVENT_BUS_SCHEMAS.md §6.2).

The DLQ record wraps the failed event *unchanged* and appends triage metadata;
error strings are sanitized so no PHI leaks into the failure envelope.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from .retry import is_transient, sanitize_error

_sentinel = object()


def failure_kind(code: str) -> str:
    return "transient" if is_transient(code) else "permanent"


def stack_digest(traceback_text: str | None) -> str | None:
    """sha256 digest of a traceback for correlation; never the raw traceback."""
    if not traceback_text:
        return None
    return hashlib.sha256(traceback_text.encode("utf-8", errors="replace")).hexdigest()


def build_failure_record(
    *,
    event_type: str,
    event_id: str,
    original_envelope: dict,
    original_topic: str,
    original_partition: int | None = None,
    original_offset: int | None = None,
    consumed_from: str,
    group_id: str,
    error_code: str,
    error_message: str,
    retry_count: int,
    traceback_text: str | None = None,
    failed_at: str | None = None,
) -> dict:
    """Build the DLQ wrapper record published to ``<topic>.dlq``."""
    if failed_at is None:
        failed_at = datetime.now(UTC).isoformat()
    return {
        "failureId": str(uuid.uuid4()),
        "originalTopic": original_topic,
        "originalPartition": original_partition,
        "originalOffset": original_offset,
        "consumedFrom": consumed_from,
        "groupId": group_id,
        "eventType": event_type if original_envelope is _sentinel else original_envelope.get("eventType", event_type),
        "failedAt": failed_at,
        "failure": {
            "code": error_code,
            "kind": failure_kind(error_code),
            "message": sanitize_error(error_message),
            "retryCount": retry_count,
            "stackDigest": stack_digest(traceback_text),
        },
        "event": {
            "eventId": event_id,
            "eventType": event_type,
            "eventVersion": original_envelope.get("eventVersion", "1"),
            "payload": original_envelope.get("payload", {}),
        },
    }