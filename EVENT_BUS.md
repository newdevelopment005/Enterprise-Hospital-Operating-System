# EVENT_BUS.md

# Enterprise Hospital Operating System (EHOS)

# Event-Driven Architecture Standard

**Version:** 1.0.0  
**Document Type:** Messaging & Event Architecture  
**Audience:** Backend Developers, Architects, DevOps Engineers, Integration Engineers

---

# 1. Purpose

This document defines the event-driven architecture for EHOS.

The event bus provides real-time communication between hospital services.

It enables:

- Real-time workflow automation
- Department synchronization
- Auditability
- Scalability
- Loose service coupling
- AI-driven intelligence

---

# 2. Event Bus Philosophy

EHOS operates as a connected healthcare ecosystem.

A hospital action should create an event.

Example:

A doctor administers medication.

The system automatically:

1. Updates clinical records
2. Reduces inventory
3. Updates billing
4. Records audit information
5. Updates analytics
6. Notifies relevant teams

---

# 3. Event Architecture

```text

                 Hospital Services


 Patient ────────┐

 EHR ────────────┤

 Pharmacy ───────┤

 Billing ────────┤

 Inventory ──────┤

 HR ─────────────┤

 AI ─────────────┤

                 │

                 ▼

            Apache Kafka

                 │

     ┌───────────┼───────────┐

     ▼           ▼           ▼

 Analytics   Notifications   Audit

```

---

# 4. Event Technology

Primary:

## Apache Kafka

Used for:

- Clinical events
- Financial events
- Inventory events
- AI events
- Audit events

---

Supporting technologies:

- Kafka Schema Registry
- Kafka Connect
- Kafka Streams

---

# 5. Event Principles

Every event must be:

## Immutable

Events cannot be modified after publishing.

---

## Versioned

Events must support future changes.

---

## Auditable

Every event has trace information.

---

## Idempotent

Duplicate events must not create duplicate actions.

---

# 6. Event Structure

All events follow a standard envelope.

Example:

```json
{
 "eventId":"8d92a1",
 "eventType":"PatientRegistered",
 "eventVersion":"1.0",
 "timestamp":"2026-01-01T10:00:00Z",
 "source":"patient-service",
 "correlationId":"abc123",
 "userId":"doctor123",
 "payload":{}
}
```

---

# 7. Required Event Fields

Every event requires:

| Field | Purpose |
|-|-|
| eventId | Unique identifier |
| eventType | Event name |
| version | Schema version |
| timestamp | Creation time |
| source | Publishing service |
| correlationId | Workflow tracking |
| userId | Initiating user |
| payload | Business data |

---

# 8. Event Naming Convention

Format:

```
EntityAction
```

Examples:

Good:

```
PatientRegistered

MedicationDispensed

InvoiceCreated

StockLevelChanged
```

Avoid:

```
patient_update_event

data_changed

process1
```

---

# 9. Kafka Topic Standards

Topics follow:

```
domain.entity.event
```

Examples:

```
clinical.patient.registered

clinical.medication.dispensed

finance.invoice.created

inventory.stock.changed

hr.employee.updated
```

---

# 10. Core Hospital Events

---

# Patient Events

Topics:

```
clinical.patient.*
```

Events:

```
PatientRegistered

PatientUpdated

PatientMerged

PatientDeceased

PatientTransferred
```

---

# Appointment Events

Topics:

```
clinical.appointment.*
```

Events:

```
AppointmentCreated

AppointmentCancelled

AppointmentCompleted

AppointmentRescheduled
```

---

# Clinical Events

Topics:

```
clinical.ehr.*
```

Events:

```
EncounterCreated

DiagnosisRecorded

ClinicalNoteCreated

TreatmentRecorded

PrescriptionCreated
```

---

# Medication Events

Topics:

```
clinical.pharmacy.*
```

Events:

```
MedicationOrdered

MedicationDispensed

MedicationReturned

MedicationExpired
```

---

# Laboratory Events

Topics:

```
clinical.lab.*
```

Events:

```
LabOrderCreated

SampleCollected

ResultAvailable

ResultVerified
```

---

# Radiology Events

Topics:

```
clinical.radiology.*
```

Events:

```
ImagingRequested

ImageCaptured

ReportCompleted
```

---

# Billing Events

Topics:

```
finance.billing.*
```

Events:

```
ChargeCreated

InvoiceGenerated

PaymentReceived

InsuranceClaimSubmitted
```

---

# Inventory Events

Topics:

```
supply.inventory.*
```

Events:

```
StockReceived

StockConsumed

StockLow

PurchaseRequested
```

---

# HR Events

Topics:

```
hr.*
```

Events:

```
EmployeeCreated

ShiftAssigned

LeaveApproved

PayrollGenerated
```

---

# AI Events

Topics:

```
ai.*
```

Events:

```
AIRequestCreated

AIResponseGenerated

ModelUpdated

PredictionGenerated
```

---

# 11. Critical Workflow Examples

---

# Medication Administration Flow

```
Doctor

↓

MedicationAdministered

↓

EHR Service

↓

Kafka

↓

Inventory Service

↓

Stock Reduced

↓

Billing Service

↓

Charge Created

↓

Analytics Service

```

---

# 12. Registration Workflow

```
Patient Registration

↓

PatientRegistered Event

↓

Appointment Service

↓

Triage Service

↓

EHR Service

↓

Notification Service

↓

AI Risk Prediction

```

---

# 13. Inventory Automation Workflow

```
Medication Used

↓

MedicationConsumed Event

↓

Inventory Updated

↓

Stock Below Threshold

↓

StockLow Event

↓

Procurement Request

↓

Finance Approval

```

---

# 14. Event Reliability

EHOS requires:

## Retry Mechanisms

Temporary failures must retry automatically.

---

## Dead Letter Queue

Failed events move to:

```
DLQ
```

for investigation.

---

## Replay Capability

Events should be replayable for:

- Recovery
- Analytics
- System migration

---

# 15. Event Ordering

Critical events must maintain order.

Examples:

Medication:

```
Ordered

↓

Approved

↓

Dispensed

↓

Administered

```

---

# 16. Event Security

Events must include:

- Authentication
- Authorization
- Encryption
- Validation

---

Sensitive medical data should not be unnecessarily placed inside events.

Prefer:

```
Patient ID Reference

+

Secure API Retrieval

```

---

# 17. Event Storage

Kafka retention depends on purpose.

Examples:

Clinical events:

Long retention

---

Operational events:

Configurable retention

---

Audit events:

Permanent retention according to policy

---

# 18. Event Monitoring

Monitor:

- Consumer lag
- Failed messages
- Throughput
- Latency
- Broker health

---

Tools:

- Prometheus
- Grafana
- Kafka Exporter

---

# 19. Event Testing

Every event requires:

- Schema validation
- Producer tests
- Consumer tests
- Integration tests

---

# 20. Schema Management

Recommended:

Kafka Schema Registry

Formats:

- JSON Schema
- Avro
- Protobuf

---

# 21. Event Versioning

Never break existing consumers.

Example:

Version 1:

```json
{
"name":"John"
}
```

Version 2:

```json
{
"firstName":"John",
"lastName":"Smith"
}
```

Both versions must be supported during migration.

---

# 22. AI Event Processing

AI systems can consume events for:

- Forecasting
- Alerts
- Optimization
- Analytics

Example:

```
PatientAdmission Event

↓

AI Prediction Agent

↓

Bed Demand Forecast

```

---

# 23. Disaster Recovery

Kafka must support:

- Replication
- Backup
- Recovery testing
- Cluster monitoring

---

# 24. Forbidden Practices

Never:

❌ Directly couple services

❌ Modify published events

❌ Store excessive patient data in messages

❌ Ignore failed events

❌ Create undocumented events

❌ Create duplicate business processing

---

# 25. Final Event Architecture Principle

> Events are the communication language of EHOS. Every hospital action should create a reliable, secure, traceable digital signal that allows the entire healthcare ecosystem to respond intelligently.