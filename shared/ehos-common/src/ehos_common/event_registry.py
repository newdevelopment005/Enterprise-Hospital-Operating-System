"""Event Registry — topic catalog, retry policies, retention, and JSON-Schema validation.

Mirrors EVENT_BUS_SCHEMAS.md: envelope + payload conform to one Schema-Registry
schema per topic (subject ``<topic>-value``), retry tiers per event class, and
retention by topic group. Validation is offline (no Kafka needed) so consumers
and producers can gate on the same contract.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import jsonschema

from .errors import SchemaValidationError, UnknownEventTypeError
from .retry import RetryPolicy

ENVELOPE_REQUIRED = [
    "eventId",
    "eventType",
    "eventVersion",
    "timestamp",
    "source",
    "correlationId",
    "userId",
    "payload",
]

_RETRY_CLINICAL = RetryPolicy(max_attempts=4, delays_seconds=(1, 10, 60))
_RETRY_FINANCE = RetryPolicy(max_attempts=5, delays_seconds=(1, 10, 60, 300))


def _wrap_schema(event_type: str, payload: dict) -> dict:
    """Assemble the full message schema from an envelope template + payload definition."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"EHOS {event_type}",
        "type": "object",
        "required": ENVELOPE_REQUIRED,
        "properties": {
            "eventId": {"type": "string", "format": "uuid"},
            "eventType": {"const": event_type},
            "eventVersion": {"type": "string"},
            "timestamp": {"type": "string", "format": "date-time"},
            "source": {"type": "string"},
            "correlationId": {"type": ["string", "null"]},
            "userId": {"type": ["string", "null"]},
            "payload": payload,
        },
        "additionalProperties": False,
    }


def _payload(program: str, *, required: tuple[str, ...], **properties) -> dict:
    return {
        "type": "object",
        "required": list(required),
        "properties": properties,
        # Payloads are forward-compatible: producers may enrich a payload with
        # optional fields (e.g. display names) without breaking the contract.
        # Required fields + types stay enforced; envelope-level strictness is
        # preserved by ``_wrap_schema``.
        "additionalProperties": True,
        "title": program,
    }


_UUID = {"type": "string", "format": "uuid"}
_TS = {"type": "string", "format": "date-time"}

DOC_TYPES_KNOWLEDGE = (
    "GUIDELINE",
    "POLICY",
    "PROTOCOL",
    "FORMULARY",
    "TEXTBOOK",
    "REGULATORY",
    "PATIENT_ED",
    "MEDICATION",
    "LAB_REFERENCE",
    "JOURNAL",
)


def _schemas() -> dict[str, dict]:
    """Full message JSON Schema per registered eventType (topic-order below)."""
    return {
        # --- clinical.patient.registered (patient-service) ---
        "PatientRegistered": _wrap_schema(
            "PatientRegistered",
            _payload(
                "payload",
                required=("patientId", "mrn", "registeredAt"),
                patientId=_UUID,
                mrn={"type": "string", "examples": ["MRN-2026-0001"]},
                registeredAt=_TS,
                registrationBranch={"type": "string"},
                sourceSystem={"type": "string"},
            ),
        ),
        # --- clinical.patient.updated (patient-service) ---
        "PatientUpdated": _wrap_schema(
            "PatientUpdated",
            _payload(
                "payload",
                required=("patientId", "occurredAt"),
                patientId=_UUID,
                occurredAt=_TS,
                fields={"type": "array", "items": {"type": "string"}},
                actorId=_UUID,
                sourceSystem={"type": "string"},
            ),
        ),
        # --- clinical.patient.merged (patient-service) ---
        "PatientMerged": _wrap_schema(
            "PatientMerged",
            _payload(
                "payload",
                required=("patientId", "mergedId", "occurredAt"),
                patientId=_UUID,
                mergedId=_UUID,
                duplicateMrn={"type": "string"},
                occurredAt=_TS,
            ),
        ),
        # --- clinical.patient.deactivated (patient-service) ---
        "PatientDeactivated": _wrap_schema(
            "PatientDeactivated",
            _payload(
                "payload",
                required=("patientId", "occurredAt"),
                patientId=_UUID,
                mergedInto=_UUID,
                occurredAt=_TS,
            ),
        ),
        # --- configuration.updated (configuration-service) ---
        "ConfigurationUpdated": _wrap_schema(
            "ConfigurationUpdated",
            _payload(
                "payload",
                required=("configKey",),
                configKey={"type": "string"},
                value={"type": ["string", "number", "boolean", "object", "null"]},
                updatedAt=_TS,
            ),
        ),
        # --- clinical.ehr.record.updated (ehr-service) ---
        "ClinicalRecordUpdated": _wrap_schema(
            "ClinicalRecordUpdated",
            _payload(
                "payload",
                required=("patientId", "eventType", "occurredAt"),
                patientId=_UUID,
                eventType={"type": "string"},
                occurredAt=_TS,
                recordId=_UUID,
                recordType={"type": "string"},
                source={"type": "string"},
                actorId=_UUID,
                details={"type": "object"},
            ),
        ),
        # --- clinical.appointment.created (scheduling-service) ---
        "AppointmentCreated": _wrap_schema(
            "AppointmentCreated",
            _payload(
                "payload",
                required=("appointmentId", "patientId", "providerId", "startAt", "status"),
                appointmentId=_UUID,
                patientId=_UUID,
                providerId=_UUID,
                department={"type": "string"},
                startAt=_TS,
                endAt=_TS,
                status={"type": "string", "enum": ["SCHEDULED", "CONFIRMED", "CANCELLED", "COMPLETED", "NO_SHOW"]},
            ),
        ),
        # --- clinical.lab.order.created (laboratory-service) ---
        "LabOrdered": _wrap_schema(
            "LabOrdered",
            _payload(
                "payload",
                required=("labOrderId", "patientId", "ordererId", "priority", "panel"),
                labOrderId=_UUID,
                patientId=_UUID,
                ordererId=_UUID,
                panel={"type": "array", "items": {"type": "string"}},
                priority={"type": "string", "enum": ["ROUTINE", "URGENT", "STAT"]},
                orderedAt=_TS,
                collectionLocation={"type": "string"},
            ),
        ),
        # --- clinical.pharmacy.medication.dispensed (pharmacy-service) ---
        "MedicationDispensed": _wrap_schema(
            "MedicationDispensed",
            _payload(
                "payload",
                required=(
                    "dispenseId",
                    "prescriptionId",
                    "patientId",
                    "medicationCode",
                    "quantity",
                    "dispensedAt",
                    "dispensedBy",
                ),
                dispenseId=_UUID,
                prescriptionId=_UUID,
                patientId=_UUID,
                medicationCode={"type": "string"},
                quantity={"type": "number"},
                unit={"type": "string", "enum": ["TABLET", "CAPSULE", "ML", "MG", "VIAL", "PATCH"]},
                pharmacyId=_UUID,
                dispensedAt=_TS,
                dispensedBy=_UUID,
            ),
        ),
        # --- supply.inventory.updated (inventory-service) ---
        "InventoryUpdated": _wrap_schema(
            "InventoryUpdated",
            _payload(
                "payload",
                required=("itemId", "sku", "delta", "newLevel", "reorderPoint", "updatedAt", "updatedBy"),
                itemId=_UUID,
                sku={"type": "string"},
                delta={"type": "number"},
                newLevel={"type": "number"},
                available={"type": "number"},
                reorderPoint={"type": "number"},
                location={"type": "string"},
                updatedAt=_TS,
                updatedBy=_UUID,
            ),
        ),
        # --- finance.billing.generated (billing-service) ---
        "BillGenerated": _wrap_schema(
            "BillGenerated",
            _payload(
                "payload",
                required=("invoiceId", "patientId", "billNumber", "currency", "totalAmount", "generatedAt", "status"),
                invoiceId=_UUID,
                patientId=_UUID,
                billNumber={"type": "string"},
                currency={"type": "string", "minLength": 3, "maxLength": 3},
                totalAmount={"type": "number"},
                lineItemCount={"type": "integer"},
                generatedAt=_TS,
                status={"type": "string", "enum": ["DRAFT", "ISSUED", "PAID", "VOIDED", "PARTIAL"]},
            ),
        ),
        # --- hr.payroll.completed (payroll-service) ---
        "PayrollCompleted": _wrap_schema(
            "PayrollCompleted",
            _payload(
                "payload",
                required=("runId", "periodFrom", "periodTo", "employeeId", "netPay", "completedAt", "status"),
                runId=_UUID,
                periodFrom={"type": "string", "format": "date"},
                periodTo={"type": "string", "format": "date"},
                employeeId=_UUID,
                netPay={"type": "number"},
                currency={"type": "string", "minLength": 3, "maxLength": 3},
                completedAt=_TS,
                status={"type": "string", "enum": ["COMPLETED", "PAID", "ERROR"]},
            ),
        ),
        # --- clinical.emergency.triggered (emergency-service) ---
        "EmergencyTriggered": _wrap_schema(
            "EmergencyTriggered",
            _payload(
                "payload",
                required=("emergencyId", "patientId", "severity", "triggeredAt", "status"),
                emergencyId=_UUID,
                patientId={"type": ["string", "null"], "format": "uuid"},
                severity={"type": "string", "enum": ["LOW", "MODERATE", "HIGH", "CRITICAL"]},
                category={"type": "string"},
                location={"type": "string"},
                triggeredAt=_TS,
                acknowledgedBy={"type": ["string", "null"], "format": "uuid"},
                status={"type": "string", "enum": ["ACTIVE", "ACKNOWLEDGED", "RESOLVED"]},
            ),
        ),
        # --- knowledge.document.ingested (knowledge-service) ---
        "KnowledgeDocumentIngested": _wrap_schema(
            "KnowledgeDocumentIngested",
            _payload(
                "payload",
                required=("documentId", "docType", "ingestedAt"),
                documentId=_UUID,
                docType={
                    "type": "string",
                    "enum": DOC_TYPES_KNOWLEDGE,
                },
                ingestedAt=_TS,
                title={"type": "string"},
                wordCount={"type": "integer", "minimum": 0},
            ),
        ),
        # --- ai.* (ai-service) ---
        "AIRequestCreated": _wrap_schema(
            "AIRequestCreated",
            _payload(
                "payload",
                required=("requestId", "contextType", "status"),
                requestId=_UUID,
                contextType={"type": "string", "enum": ["CHAT", "AGENT", "RAG_QUERY", "MEDIA"]},
                userId={"type": ["string", "null"]},
                status={"type": "string", "enum": ["PROCESSING", "COMPLETED", "FAILED"]},
            ),
        ),
        "AIResponseGenerated": _wrap_schema(
            "AIResponseGenerated",
            _payload(
                "payload",
                required=("requestId", "model", "latencyMs", "status"),
                requestId=_UUID,
                model={"type": "string"},
                latencyMs={"type": "integer", "minimum": 0},
                status={"type": "string", "enum": ["OK", "TRUNCATED", "FAILED"]},
            ),
        ),
        # --- ai.prediction.generated (prediction-service) ---
        "PredictionGenerated": _wrap_schema(
            "PredictionGenerated",
            _payload(
                "payload",
                required=("predictionKey", "entityType", "entityId", "generatedAt"),
                predictionKey={"type": "string"},
                entityType={"type": "string"},
                entityId={"type": "string"},
                horizon={"type": ["string", "null"]},
                generatedAt=_TS,
            ),
        ),
    }


@dataclass(frozen=True)
class EventMeta:
    event_type: str
    topic: str
    source_service: str
    ordering_key: str
    retention_days: int
    retry_policy: RetryPolicy
    schema: dict
    validator: Callable[[dict], None]


CLINICAL_TOPICS = 180
SUPPLY_TOPICS = 90
FINANCE_TOPICS = 365 * 7
HR_TOPICS = 365 * 7
DLQ_RETENTION_DAYS = 60

_CATALOG: dict[str, tuple[str, str, str, int, RetryPolicy]] = {
    # eventType: (topic, source_service, ordering_key, retention_days, retry_policy)
    "PatientRegistered": (
        "clinical.patient.registered",
        "patient-service",
        "payload.patientId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "PatientUpdated": (
        "clinical.patient.updated",
        "patient-service",
        "payload.patientId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "PatientMerged": (
        "clinical.patient.merged",
        "patient-service",
        "payload.patientId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "PatientDeactivated": (
        "clinical.patient.deactivated",
        "patient-service",
        "payload.patientId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "ConfigurationUpdated": (
        "configuration.topic",
        "configuration-service",
        "payload.configKey",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "AppointmentCreated": (
        "clinical.appointment.created",
        "scheduling-service",
        "payload.patientId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "ClinicalRecordUpdated": (
        "clinical.ehr.record.updated",
        "ehr-service",
        "payload.patientId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "LabOrdered": (
        "clinical.lab.order.created",
        "laboratory-service",
        "payload.labOrderId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "MedicationDispensed": (
        "clinical.pharmacy.medication.dispensed",
        "pharmacy-service",
        "payload.patientId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "EmergencyTriggered": (
        "clinical.emergency.triggered",
        "emergency-service",
        "payload.emergencyId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "InventoryUpdated": (
        "supply.inventory.updated",
        "inventory-service",
        "payload.itemId",
        SUPPLY_TOPICS,
        _RETRY_CLINICAL,
    ),
    "BillGenerated": (
        "finance.billing.generated",
        "billing-service",
        "payload.invoiceId",
        FINANCE_TOPICS,
        _RETRY_FINANCE,
    ),
    "PayrollCompleted": (
        "hr.payroll.completed",
        "payroll-service",
        "payload.runId",
        HR_TOPICS,
        _RETRY_FINANCE,
    ),
    "KnowledgeDocumentIngested": (
        "knowledge.document.ingested",
        "knowledge-service",
        "payload.documentId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "AIRequestCreated": (
        "ai.request.created",
        "ai-service",
        "payload.requestId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "AIResponseGenerated": (
        "ai.response.generated",
        "ai-service",
        "payload.requestId",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
    "PredictionGenerated": (
        "ai.prediction.generated",
        "prediction-service",
        "payload.predictionKey",
        CLINICAL_TOPICS,
        _RETRY_CLINICAL,
    ),
}


class EventRegistry:
    """Holds the contract for every registered eventType and validates messages."""

    def __init__(self, schemas: dict[str, dict] | None = None, catalog: dict[str, tuple] | None = None) -> None:
        schemas = schemas if schemas is not None else _schemas()
        catalog = catalog if catalog is not None else _CATALOG
        self._meta: dict[str, EventMeta] = {}
        for event_type, (topic, source, ordering_key, retention, retry_policy) in catalog.items():
            if event_type not in schemas:
                raise ValueError(f"Catalog entry {event_type!r} has no schema")
            schema = schemas[event_type]
            self._meta[event_type] = EventMeta(
                event_type=event_type,
                topic=topic,
                source_service=source,
                ordering_key=ordering_key,
                retention_days=retention,
                retry_policy=retry_policy,
                schema=schema,
                validator=_make_validator(schema),
            )

    @property
    def event_types(self) -> tuple[str, ...]:
        return tuple(self._meta)

    def known(self, event_type: str) -> bool:
        return event_type in self._meta

    def __getitem__(self, event_type: str) -> EventMeta:
        if event_type not in self._meta:
            raise UnknownEventTypeError(f"Event type {event_type!r} is not registered")
        return self._meta[event_type]

    def topic(self, event_type: str) -> str:
        return self[event_type].topic

    def retention_days(self, event_type: str) -> int:
        return self[event_type].retention_days

    def retry_policy(self, event_type: str) -> RetryPolicy:
        return self[event_type].retry_policy

    def retry_topic(self, event_type: str, failed_attempt: int) -> str:
        meta = self[event_type]
        return meta.retry_policy.retry_topic(meta.topic, failed_attempt)

    def dlq_topic(self, event_type: str) -> str:
        return self.retry_policy(event_type).dlq_topic(self.topic(event_type))

    def topics_for(self, event_types: list[str]) -> list[str]:
        """Main topic plus every retry tier for the given eventTypes (for consumer subscription)."""
        topics: list[str] = []
        for event_type in event_types:
            meta = self[event_type]
            topics.append(meta.topic)
            topics.extend(
                meta.retry_policy.retry_topic(meta.topic, i + 1) for i in range(len(meta.retry_policy.delays_seconds))
            )
        return topics

    def validate(self, message: dict) -> None:
        """Validate a parsed envelope. Raises SchemaValidationError / UnknownEventTypeError."""
        if not isinstance(message, dict) or "eventType" not in message:
            raise SchemaValidationError("Envelope missing required field 'eventType'")
        event_type = message["eventType"]
        try:
            meta = self[event_type]
        except UnknownEventTypeError:
            raise
        try:
            meta.validator(message)
        except jsonschema.ValidationError as exc:
            path = ".".join(str(p) for p in exc.absolute_path) or "$"
            raise SchemaValidationError(f"Event {event_type!r} fails schema at {path}: {exc.message}") from exc


def _make_validator(schema: dict) -> Callable[[dict], None]:
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema)

    def validate(message: dict) -> None:
        validator.validate(message)

    return validate