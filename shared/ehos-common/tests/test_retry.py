"""Retry policy + header block tests (EVENT_BUS_SCHEMAS.md §5)."""

from __future__ import annotations

from ehos_common.retry import (
    BUSINESS_REJECTED,
    CONSUMER_ERROR,
    INVALID_SCHEMA,
    UNKNOWN_EVENT_TYPE,
    RetryPolicy,
    build_retry_headers,
    is_permanent,
    is_transient,
    parse_retry_headers,
    retry_count_from_headers,
    sanitize_error,
)


def test_code_taxonomy():
    assert is_permanent(INVALID_SCHEMA)
    assert is_permanent(BUSINESS_REJECTED)
    assert is_permanent(UNKNOWN_EVENT_TYPE)
    assert is_transient(CONSUMER_ERROR)
    assert not is_transient(INVALID_SCHEMA)
    assert is_transient("THROTTLED")


def test_retry_tiers_clinical():
    policy = RetryPolicy(max_attempts=4, delays_seconds=(1, 10, 60))
    assert policy.retry_topic("clinical.patient.registered", 1) == "clinical.patient.registered.retry.1s"
    assert policy.retry_topic("clinical.patient.registered", 2) == "clinical.patient.registered.retry.10s"
    assert policy.retry_topic("clinical.patient.registered", 3) == "clinical.patient.registered.retry.60s"
    assert policy.dlq_topic("clinical.patient.registered") == "clinical.patient.registered.dlq"


def test_should_dlq_boundary():
    policy = RetryPolicy(max_attempts=4, delays_seconds=(1, 10, 60))
    assert not policy.should_dlq(1, CONSUMER_ERROR)
    assert not policy.should_dlq(3, CONSUMER_ERROR)
    assert policy.should_dlq(4, CONSUMER_ERROR)
    assert policy.should_dlq(1, INVALID_SCHEMA)


def test_backoff_within_jitter_bounds():
    policy = RetryPolicy(max_attempts=4, delays_seconds=(1, 10, 60), jitter_fraction=0.2)
    for attempt in (1, 2, 3, 9):
        delay = policy.backoff_seconds(attempt, jitter=True)
        nominal = policy.tier_delay(attempt)
        assert nominal * 0.8 <= delay <= nominal * 1.2


def test_retry_headers_roundtrip():
    headers = build_retry_headers(retry_count=2, reason="ValueError: boom", max_attempts=4)
    parsed = parse_retry_headers(headers)
    assert parsed["X-EHOS-RetryCount"] == "2"
    assert parsed["X-EHOS-MaxAttempts"] == "4"
    assert "boom" in parsed["X-EHOS-RetryReason"]
    assert retry_count_from_headers(headers) == 2


def test_parse_retry_headers_is_case_insensitive():
    parsed = parse_retry_headers([("x-ehos-retrycount", "1"), ("Content-Type", "application/json")])
    assert parsed["X-EHOS-RetryCount"] == "1"
    assert "Content-Type" not in parsed


def test_retry_count_from_mixed_headers():
    headers = [("content-type", "application/json"), ("X-EHOS-RetryCount", "3")]
    assert retry_count_from_headers(headers) == 3
    assert retry_count_from_headers(None) == 0
    assert retry_count_from_headers([("X-EHOS-RetryCount", "not-a-number")]) == 0


def test_sanitize_error_flattens_truncates_and_redacts():
    assert sanitize_error("a  b \n c") == "a b c"
    assert sanitize_error("mrn=MRN-2026-0001") == "[redacted]"
    long = "word " * 100
    out = sanitize_error(long)
    assert len(out) <= 240
    assert out.endswith("...")