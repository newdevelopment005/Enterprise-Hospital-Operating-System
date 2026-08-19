"""EventRegistry contract + schema validation tests."""

from __future__ import annotations

import pytest
from conftest import make_envelope

from ehos_common.errors import SchemaValidationError, UnknownEventTypeError
from ehos_common.event_registry import EventRegistry


def test_catalog_fully_specified():
    registry = EventRegistry()
    assert set(registry.event_types) == {
        "PatientRegistered",
        "PatientUpdated",
        "PatientMerged",
        "PatientDeactivated",
        "AppointmentCreated",
        "LabOrdered",
        "MedicationDispensed",
        "InventoryUpdated",
        "BillGenerated",
        "PayrollCompleted",
        "EmergencyTriggered",
        "KnowledgeDocumentIngested",
        "AIRequestCreated",
        "AIResponseGenerated",
        "PredictionGenerated",
        "ClinicalRecordUpdated",
        "ConfigurationUpdated",
    }


def test_patient_domain_event_topics_locked():
    """patient-service must publish on the canonical registry topics."""
    registry = EventRegistry()
    assert registry.topic("PatientRegistered") == "clinical.patient.registered"
    assert registry.topic("PatientUpdated") == "clinical.patient.updated"
    assert registry.topic("PatientMerged") == "clinical.patient.merged"
    assert registry.topic("PatientDeactivated") == "clinical.patient.deactivated"


def test_topic_retention_retry(registry: EventRegistry):
    assert registry.topic("PatientRegistered") == "clinical.patient.registered"
    assert registry.topic("BillGenerated") == "finance.billing.generated"
    assert registry.retention_days("PatientRegistered") == 180
    assert registry.retention_days("PayrollCompleted") == 365 * 7
    assert registry.retry_topic("PatientRegistered", 1) == "clinical.patient.registered.retry.1s"
    assert registry.dlq_topic("PatientRegistered") == "clinical.patient.registered.dlq"
    assert registry.retry_policy("BillGenerated").max_attempts == 5


def test_topics_for_matches_retry_ladder():
    clinical = EventRegistry().topics_for(["PatientRegistered", "LabOrdered"])
    assert "clinical.patient.registered" in clinical
    assert "clinical.patient.registered.retry.1s" in clinical
    assert "clinical.patient.registered.retry.60s" in clinical
    assert "clinical.lab.order.created" in clinical
    assert "clinical.lab.order.created.retry.60s" in clinical
    finance = EventRegistry().topics_for(["PayrollCompleted"])
    assert "hr.payroll.completed.retry.300s" in finance


def test_validate_good_envelope(registry: EventRegistry):
    registry.validate(make_envelope("PatientRegistered"))
    registry.validate(make_envelope("PatientUpdated"))
    registry.validate(make_envelope("PatientMerged", duplicateMrn="MRN-2026-0002"))
    registry.validate(make_envelope("PatientDeactivated", mergedInto="00000000-0000-0000-0000-000000000000"))
    registry.validate(make_envelope("ConfigurationUpdated", value={"surcharge": 0.05}))
    registry.validate(make_envelope("MedicationDispensed"))
    registry.validate(make_envelope("PayrollCompleted"))
    registry.validate(make_envelope("KnowledgeDocumentIngested"))


def test_validate_unknown_event_type(registry: EventRegistry):
    with pytest.raises(UnknownEventTypeError):
        registry.validate({"eventType": "NoSuchEvent", "payload": {}})


def test_validate_missing_required_field(registry: EventRegistry):
    with pytest.raises(SchemaValidationError) as exc:
        registry.validate(make_envelope("PatientRegistered", patientId=None))
    assert "fails schema" in str(exc.value)


def test_validate_missing_envelope_field(registry: EventRegistry):
    with pytest.raises(SchemaValidationError):
        registry.validate(make_envelope("PatientRegistered", drop=["timestamp"]))


def test_extra_payload_field_is_forward_compatible(registry: EventRegistry):
    # Payloads are forward-compatible (producers enrich with optional fields);
    # required payload fields are still enforced (see missing-required test).
    registry.validate(make_envelope("PatientRegistered", ssn="123-45-6789"))


def test_validate_wrong_event_version_value(registry: EventRegistry):
    registry.validate(make_envelope("PatientRegistered", event_version="1"))
    # version is a free string in the envelope; consumers branch on it
    registry.validate(make_envelope("PatientRegistered", event_version="2"))