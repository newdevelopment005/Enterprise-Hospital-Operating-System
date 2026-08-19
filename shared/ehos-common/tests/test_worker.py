"""EventProcessor tests: validate -> dispatch -> retry ladder -> DLQ."""

from __future__ import annotations

import asyncio
import json

from conftest import FakeConsumer, FakePublisher, fake_ok_handler, make_envelope

from ehos_common import EventProcessor, EventRegistry
from ehos_common.errors import EventBusError, HandlerRejectedError
from ehos_common.retry import CONSUMER_ERROR, INVALID_SCHEMA, UNKNOWN_EVENT_TYPE
from ehos_common.worker import Record


class AlwaysFail:
    def __init__(self, code: str = CONSUMER_ERROR) -> None:
        self.code = code
        self.calls = 0

    async def __call__(self, envelope: dict, *, record: Record) -> None:
        self.calls += 1
        raise EventBusError("simulated downstream failure", code=self.code)


def make_processor(
    publisher: FakePublisher,
    handlers: dict,
    *,
    registry: EventRegistry | None = None,
) -> EventProcessor:
    return EventProcessor(
        consumer=FakeConsumer([]),
        publisher=publisher,
        registry=registry or EventRegistry(),
        handlers=handlers,
        group_id="test-group",
    )


async def test_consume_success(publisher: FakePublisher, make_record):
    proc = make_processor(publisher, {"PatientRegistered": fake_ok_handler})
    envelope = make_envelope("PatientRegistered")
    outcome = await proc.process_record(make_record(envelope))
    assert outcome.status == "consumed"
    assert publisher.published == []
    assert proc.processed == 1


async def test_no_handler_is_ignored(publisher: FakePublisher, make_record):
    proc = make_processor(publisher, {"PatientRegistered": fake_ok_handler})
    outcome = await proc.process_record(make_record(make_envelope("AppointmentCreated")))
    assert outcome.status == "ignored"
    assert publisher.published == []


async def test_transient_retry_ladder_then_dlq(publisher: FakePublisher, make_record):
    proc = make_processor(publisher, {"PatientRegistered": AlwaysFail()})
    envelope = make_envelope("PatientRegistered")
    current = make_record(envelope)
    ladder = [
        "clinical.patient.registered.retry.1s",
        "clinical.patient.registered.retry.10s",
        "clinical.patient.registered.retry.60s",
        "clinical.patient.registered.dlq",
    ]
    outcomes = []
    for step, _dest in enumerate(ladder):
        outcomes.append(await proc.process_record(current))
        topic, republished, headers = publisher.published[step]
        current = make_record(republished, topic=topic, headers=headers)

    assert [o.status for o in outcomes] == ["retried", "retried", "retried", "dlq"]
    assert [o.dest_topic for o in outcomes] == ladder
    assert publisher.published[0][2][0][0] == "X-EHOS-RetryCount" and publisher.published[0][2][0][1] == "1"
    assert publisher.published[1][2][0][1] == "2"
    assert publisher.published[2][2][0][1] == "3"

    failure = publisher.published[3][1]
    assert failure["failure"]["code"] == CONSUMER_ERROR
    assert failure["failure"]["retryCount"] == 3
    assert failure["event"]["eventId"] == envelope["eventId"]
    assert failure["originalTopic"] == "clinical.patient.registered"
    # DLQ publish must carry headers as a list of (key, value) tuples for the
    # real Kafka producer (a dict would fail to unpack).
    dlq_headers = publisher.published[3][2]
    assert isinstance(dlq_headers, list)
    assert all(isinstance(h, tuple) and len(h) == 2 for h in dlq_headers)
    assert dict(dlq_headers).get("X-EHOS-RetryCount") == "3"


async def test_permanent_business_reject_goes_straight_to_dlq(publisher: FakePublisher, make_record):
    async def reject_handler(envelope: dict, *, record: Record) -> None:
        raise HandlerRejectedError("Entity not found in domain reference data")

    proc = make_processor(publisher, {"PatientRegistered": reject_handler})
    outcome = await proc.process_record(make_record(make_envelope("PatientRegistered")))
    assert outcome.status == "dlq"
    assert outcome.dest_topic == "clinical.patient.registered.dlq"
    failure = publisher.published[0][1]
    assert failure["failure"]["code"] == "BUSINESS_REJECTED"
    assert failure["failure"]["kind"] == "permanent"


async def test_schema_violation_goes_to_dlq(publisher: FakePublisher, make_record):
    proc = make_processor(publisher, {"PatientRegistered": fake_ok_handler})
    envelope = make_envelope("PatientRegistered", drop=["mrn"])
    outcome = await proc.process_record(make_record(envelope))
    assert outcome.status == "dlq"
    assert outcome.dest_topic == "clinical.patient.registered.dlq"
    assert publisher.published[0][1]["failure"]["code"] == INVALID_SCHEMA


async def test_unknown_event_type_with_handler_goes_to_dlq(publisher: FakePublisher, make_record):
    async def handler(envelope: dict, *, record: Record) -> None:
        return None

    proc = make_processor(publisher, {"MysteryEvent": handler})
    envelope = {"eventType": "MysteryEvent", "payload": {"x": 1}}
    outcome = await proc.process_record(make_record(envelope, topic="mystery.topic"))
    assert outcome.status == "dlq"
    assert outcome.dest_topic == "mystery.topic.dlq"
    assert publisher.published[0][1]["failure"]["code"] == UNKNOWN_EVENT_TYPE


async def test_undecodable_body_goes_to_dlq(publisher: FakePublisher, make_record):
    proc = make_processor(publisher, {"PatientRegistered": fake_ok_handler})
    outcome = await proc.process_record(make_record(None, raw="this is not json", topic="clinical.patient.registered"))
    assert outcome.status == "dlq"
    assert outcome.dest_topic == "clinical.patient.registered.dlq"
    assert publisher.published[0][1]["failure"]["code"] == INVALID_SCHEMA


async def test_retry_message_completes_on_later_attempt(publisher: FakePublisher, make_record):
    proc = make_processor(publisher, {"PatientRegistered": fake_ok_handler})
    envelope = make_envelope("PatientRegistered")
    retry_headers = [("X-EHOS-RetryCount", "1"), ("X-EHOS-RetryReason", "CONSUMER_ERROR")]
    outcome = await proc.process_record(
        make_record("clinical.patient.registered.retry.1s", headers=retry_headers, raw=json.dumps(envelope))
    )
    assert outcome.status == "consumed"
    assert publisher.published == []


async def test_run_loop_consumes_and_commits(publisher: FakePublisher, make_record):
    envelopes = [make_envelope("PatientRegistered"), make_envelope("LabOrdered")]
    consumer = FakeConsumer([make_record(envelopes[0]), make_record(envelopes[1], topic="clinical.lab.order.created")])
    proc = EventProcessor(
        consumer=consumer,
        publisher=publisher,
        registry=EventRegistry(),
        handlers={"PatientRegistered": fake_ok_handler, "LabOrdered": fake_ok_handler},
        group_id="test-group",
    )
    stop = asyncio.Event()
    task = asyncio.create_task(proc.run(stop=stop))
    await asyncio.wait_for(task, timeout=5)
    assert consumer.commits == 2
    assert proc.processed == 2
    assert proc.failed == 0
    await asyncio.sleep(0)
    stop.set()