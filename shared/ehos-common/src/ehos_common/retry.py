"""Retry policies and the EHOS failure-code taxonomy for the event bus.

Implemented per EVENT_BUS_SCHEMAS.md §5 and §6: retry transient failures only,
exponential backoff with jitter, route through ``<topic>.retry.<delay>`` tiers,
and land abused attempts or permanent failures on ``<topic>.dlq``.
"""

import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime

INVALID_SCHEMA = "INVALID_SCHEMA"
UNKNOWN_EVENT_TYPE = "UNKNOWN_EVENT_TYPE"
AUTHZ_DENIED = "AUTHZ_DENIED"
BUSINESS_REJECTED = "BUSINESS_REJECTED"
CONSUMER_ERROR = "CONSUMER_ERROR"
OUT_OF_RETRIES = "OUT_OF_RETRIES"

PERMANENT_CODES = frozenset({INVALID_SCHEMA, UNKNOWN_EVENT_TYPE, AUTHZ_DENIED, BUSINESS_REJECTED})
TRANSIENT_CODES = frozenset(
    {
        CONSUMER_ERROR,
        OUT_OF_RETRIES,
        "TIMEOUT",
        "THROTTLED",
        "SERVICE_UNAVAILABLE",
        "DATABASE_UNAVAILABLE",
    }
)


def is_transient(code: str) -> bool:
    """Whether a failure code is retryable. Unknown codes default to transient-safe."""
    return code not in PERMANENT_CODES


def is_permanent(code: str) -> bool:
    return code in PERMANENT_CODES


HEADER_RETRY_COUNT = "X-EHOS-RetryCount"
HEADER_RETRY_REASON = "X-EHOS-RetryReason"
HEADER_LAST_ATTEMPT_AT = "X-EHOS-LastAttemptAt"
HEADER_MAX_ATTEMPTS = "X-EHOS-MaxAttempts"

_RETRY_HEADER_LOOKUP = {
    header.upper(): header
    for header in (HEADER_RETRY_COUNT, HEADER_RETRY_REASON, HEADER_LAST_ATTEMPT_AT, HEADER_MAX_ATTEMPTS)
}


def build_retry_headers(
    *,
    retry_count: int,
    reason: str,
    max_attempts: int,
    last_attempt_at: str | None = None,
) -> list[tuple[str, str]]:
    """Header block appended to every republish (EVENT_BUS_SCHEMAS.md §5.3)."""
    if last_attempt_at is None:
        last_attempt_at = datetime.now(UTC).isoformat()
    return [
        (HEADER_RETRY_COUNT, str(retry_count)),
        (HEADER_RETRY_REASON, sanitize_error(reason)),
        (HEADER_LAST_ATTEMPT_AT, last_attempt_at),
        (HEADER_MAX_ATTEMPTS, str(max_attempts)),
    ]


def parse_retry_headers(headers: list[tuple[str, str]] | None) -> dict[str, str]:
    """Case-insensitive dict of the X-EHOS-* retry headers on a consumed record.

    Keys use the canonical (mixed-case) header names, so callers always read
    ``X-EHOS-RetryCount`` etc. regardless of the wire casing.
    """
    out: dict[str, str] = {}
    for key, value in headers or []:
        canonical = _RETRY_HEADER_LOOKUP.get(key.upper())
        if canonical is not None:
            out[canonical] = value
    return out


def retry_count_from_headers(headers: list[tuple[str, str]] | None) -> int:
    parsed = parse_retry_headers(headers)
    try:
        return max(int(parsed.get(HEADER_RETRY_COUNT, 0)), 0)
    except (TypeError, ValueError):
        return 0


_PHI_KV = re.compile(
    r"\b(?:mrn|name|patient name|diagnosis|attending|ssn|dob|phone|insurance|address)"
    r"\s*=\s*[^\s,;]+",
    re.IGNORECASE,
)


def sanitize_error(message: str, limit: int = 240) -> str:
    """Sanitize + truncate an error string for headers/failure records (no PHI).

    Flattens whitespace, redacts common ``key=value`` PHI markers, and truncates
    to ``limit`` chars so no sensitive or massive detail leaks into the DLQ.
    """
    cleaned = " ".join(str(message).split())
    cleaned = _PHI_KV.sub("[redacted]", cleaned)
    if len(cleaned) > limit:
        return cleaned[: limit - 3] + "..."
    return cleaned


@dataclass(frozen=True)
class RetryPolicy:
    """Stop-and-retry ladder for one event class.

    ``failed_attempt`` is the 1-based attempt number that just failed.
    """

    max_attempts: int = 4
    delays_seconds: tuple[int, ...] = (1, 10, 60)
    jitter_fraction: float = 0.15
    _rng: random.Random = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_rng", random.Random())  # noqa: S311 - jitter only, not cryptographic

    def tier_delay(self, failed_attempt: int) -> int:
        idx = min(max(failed_attempt, 1) - 1, len(self.delays_seconds) - 1)
        return self.delays_seconds[idx]

    def retry_topic(self, base_topic: str, failed_attempt: int) -> str:
        delay = self.tier_delay(failed_attempt)
        return f"{base_topic}.retry.{delay}s"

    def dlq_topic(self, base_topic: str) -> str:
        return f"{base_topic}.dlq"

    def backoff_seconds(self, failed_attempt: int, jitter: bool = True) -> float:
        """Exponential backoff with jitter for a local sleep between retries."""
        delay = float(self.tier_delay(failed_attempt))
        if not jitter or self.jitter_fraction <= 0:
            return delay
        spread = delay * self.jitter_fraction
        return max(delay - spread + self._rng.uniform(0, 2 * spread), 0.0)

    def should_dlq(self, failed_attempt: int, error_code: str) -> bool:
        """True when a failure after ``failed_attempt`` lands on the DLQ."""
        if is_permanent(error_code):
            return True
        return failed_attempt >= self.max_attempts