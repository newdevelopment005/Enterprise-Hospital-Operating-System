"""DLQ failure envelope tests (EVENT_BUS_SCHEMAS.md §6.2)."""

from __future__ import annotations

import uuid

from conftest import make_envelope

from ehos_common.dlq import build_failure_record, failure_kind, stack_digest
from ehos_common.retry import CONSUMER_ERROR, INVALID_SCHEMA

TOO_LONG_PHI = " ".join(
    [
        "PT / MR: patient name=Jane Roe, mrn=MRN-2026-0001, diagnosis=Sickle Cell Crisis, "
        "attending=Dr Smith, full details of the encounter here"
    ]
    * 8
)


def test_failure_kind_mapping():
    assert failure_kind(CONSUMER_ERROR) == "transient"
    assert failure_kind(INVALID_SCHEMA) == "permanent"


def test_build_failure_record_shape():
    envelope = make_envelope("PatientRegistered")
    record = build_failure_record(
        event_type="PatientRegistered",
        event_id=envelope["eventId"],
        original_envelope=envelope,
        original_topic="clinical.patient.registered",
        original_partition=2,
        original_offset=10492,
        consumed_from="clinical.patient.registered.retry.60s",
        group_id="ehos-verifier-01",
        error_code=CONSUMER_ERROR,
        error_message="PSQL error: connection reset",
        retry_count=3,
    )
    assert uuid.UUID(record["failureId"])
    assert record["originalTopic"] == "clinical.patient.registered"
    assert record["originalPartition"] == 2
    assert record["originalOffset"] == 10492
    assert record["consumedFrom"].endswith(".retry.60s")
    assert record["groupId"] == "ehos-verifier-01"
    assert record["event"]["eventType"] == "PatientRegistered"
    assert record["event"]["eventId"] == envelope["eventId"]
    assert record["failure"]["code"] == CONSUMER_ERROR
    assert record["failure"]["kind"] == "transient"
    assert record["failure"]["retryCount"] == 3


def test_failure_message_sanitized_no_phi():
    envelope = make_envelope("PatientRegistered")
    record = build_failure_record(
        event_type="PatientRegistered",
        event_id=envelope["eventId"],
        original_envelope=envelope,
        original_topic="clinical.patient.registered",
        consumed_from="clinical.patient.registered",
        group_id="g",
        error_code=CONSUMER_ERROR,
        error_message=TOO_LONG_PHI,
        retry_count=0,
    )
    message = record["failure"]["message"]
    assert len(message) <= 240
    assert "diagnosis=" not in message
    assert "mrn=MRN" not in message


def test_stack_digest_is_sha256_deterministic():
    tb = "Traceback (most recent call last):\n  ValueError"
    digest = stack_digest(tb)
    assert digest == stack_digest(tb)
    assert len(digest) == 64
    assert stack_digest(None) is None