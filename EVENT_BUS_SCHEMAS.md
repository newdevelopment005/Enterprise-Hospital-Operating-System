# EVENT_BUS_SCHEMAS.md

# Enterprise Hospital Operating System (EHOS)

# Event Bus Design — Schemas, Retries, Dead-Letter Queues, Versioning

**Version:** 1.0.0
**Document Type:** Event-Driven Architecture Design / Contract Specification
**Audience:** Backend Engineers, Integration Architects, Platform/SRE Engineers, Data Governance

---

## 1. Purpose and Scope

This document is the **working contract** for the EHOS event bus, which runs on
Apache Kafka. It turns the standards in `EVENT_BUS.md` (envelope §6, required
fields §7, naming §8, topic format §9, reliability §14, schema management §20,
versioning §21) into concrete, implementable artifacts:

1. **JSON Schema for every core event** (computer-readable, Schema-Registry compatible).
2. **Retry policies** per event class.
3. **Dead-letter queues (DLQ)** — naming, failure envelope, replay, alerting.
4. **Event versioning** — evolution rules, compatibility modes, migration steps.

Only the eight requested events are fully specified here; the conventions apply
to the whole EHOS event catalog (`EVENT_BUS.md` §10).

### Governed elsewhere
| Concern | Document |
|---|---|
| Envelope + event format rules | `EVENT_BUS.md` §6–§7 |
| Naming + topic format | `EVENT_BUS.md` §8–§9 |
| Ordering | `EVENT_BUS.md` §15 |
| Security (authz, encryption, minimal data) | `EVENT_BUS.md` §16 |
| Monitoring (lag, DLQ depth, throughput) | `EVENT_BUS.md` §18 |
| Testing (schema, producer, consumer, integration) | `EVENT_BUS.md` §19 |
| Message privacy (no PHI in payload; use refs) | `EVENT_BUS.md` §16, `DATA_GOVERNANCE.md` |

---

## 2. Envelope (fixed, every event)

Every message uses the EHOS envelope from `ehos-common/events.py` and
`EVENT_BUS.md` §6:

```json
{
  "eventId": "uuid",
  "eventType": "PatientRegistered",
  "eventVersion": "1",
  "timestamp": "ISO-8601 UTC",
  "source": "<service>.<instance>",
  "correlationId": "uuid | null",
  "userId": "uuid | null",
  "payload": { }
}
```

`payload` is **deliberately minimal**: events carry global identifiers and the
snapshot deltas reacting consumers need — never full medical records. Sensitive
detail is fetched on demand via secure domain APIs (`EVENT_BUS.md` §16: prefer
*Patient ID Reference + Secure API Retrieval*).

---

## 3. Event Catalog — the Eight Core Events

| Event (eventType) | Kafka topic (`domain.entity.event`) | Source service | Ordering key |
|---|---|---|---|
| `PatientRegistered` | `clinical.patient.registered` | patient-service | `payload.patientId` |
| `AppointmentCreated` | `clinical.appointment.created` | scheduling-service | `payload.patientId` |
| `LabOrdered` | `clinical.lab.order.created` | laboratory-service | `payload.labOrderId` |
| `MedicationDispensed` | `clinical.pharmacy.medication.dispensed` | pharmacy-service | `payload.patientId` |
| `InventoryUpdated` | `supply.inventory.updated` | inventory-service | `payload.itemId` |
| `BillGenerated` | `finance.billing.generated` | billing-service | `payload.invoiceId` |
| `PayrollCompleted` | `hr.payroll.completed` | payroll-service | `payload.runId` |
| `EmergencyTriggered` | `clinical.emergency.triggered` | emergency-service | `payload.emergencyId` |

### 3.1 Topic provisioning defaults
| Setting | Default |
|---|---|
| Replication factor | 3 (`min.insync.replicas=2`) |
| Partitions | 6 per topic (scale headroom; ordering guaranteed *per key*) |
| Message capability | `max.message.bytes=1 MiB` |
| Cleanup policy | `delete` |
| Compression | `lz4` (producer `acks=all`, idempotent) |
| Retention | see §7 per event class |

Partitions key off the **ordering key** so per-entity order is preserved while
the cluster stays parallel.

---

## 4. JSON Schemas (Draft 2020-12)

Each schema is registered in the Schema Registry under subject
`<topic>-value`. The envelope and `payload` validate together as one message
value; the registry subject enforces compatibility per `eventVersion` (§8).

### 4.1 `PatientRegistered`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EHOS PatientRegistered",
  "type": "object",
  "required": ["eventId","eventType","eventVersion","timestamp","source","correlationId","userId","payload"],
  "properties": {
    "eventId": {"type": "string", "format": "uuid"},
    "eventType": {"const": "PatientRegistered"},
    "eventVersion": {"const": "1"},
    "timestamp": {"type": "string", "format": "date-time"},
    "source": {"type": "string"},
    "correlationId": {"type": ["string","null"]},
    "userId": {"type": ["string","null"]},
    "payload": {
      "type": "object",
      "required": ["patientId","mrn","registeredAt"],
      "properties": {
        "patientId": {"type": "string", "format": "uuid"},
        "mrn": {"type": "string", "examples": ["MRN-2026-0001"]},
        "registeredAt": {"type": "string", "format": "date-time"},
        "registrationBranch": {"type": "string"},
        "sourceSystem": {"type": "string"}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 4.2 `AppointmentCreated`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EHOS AppointmentCreated",
  "type": "object",
  "required": ["eventId","eventType","eventVersion","timestamp","source","correlationId","userId","payload"],
  "properties": {
    "eventId": {"type": "string", "format": "uuid"},
    "eventType": {"const": "AppointmentCreated"},
    "eventVersion": {"const": "1"},
    "timestamp": {"type": "string", "format": "date-time"},
    "source": {"type": "string"},
    "correlationId": {"type": ["string","null"]},
    "userId": {"type": ["string","null"]},
    "payload": {
      "type": "object",
      "required": ["appointmentId","patientId","providerId","startAt","status"],
      "properties": {
        "appointmentId": {"type": "string", "format": "uuid"},
        "patientId": {"type": "string", "format": "uuid"},
        "providerId": {"type": "string", "format": "uuid"},
        "department": {"type": "string"},
        "startAt": {"type": "string", "format": "date-time"},
        "endAt": {"type": "string", "format": "date-time"},
        "status": {"type": "string", "enum": ["SCHEDULED","CONFIRMED","CANCELLED","COMPLETED","NO_SHOW"]}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 4.3 `LabOrdered`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EHOS LabOrdered",
  "type": "object",
  "required": ["eventId","eventType","eventVersion","timestamp","source","correlationId","userId","payload"],
  "properties": {
    "eventId": {"type": "string", "format": "uuid"},
    "eventType": {"const": "LabOrdered"},
    "eventVersion": {"const": "1"},
    "timestamp": {"type": "string", "format": "date-time"},
    "source": {"type": "string"},
    "correlationId": {"type": ["string","null"]},
    "userId": {"type": ["string","null"]},
    "payload": {
      "type": "object",
      "required": ["labOrderId","patientId","ordererId","priority","panel"],
      "properties": {
        "labOrderId": {"type": "string", "format": "uuid"},
        "patientId": {"type": "string", "format": "uuid"},
        "ordererId": {"type": "string", "format": "uuid"},
        "panel": {"type": "array", "items": {"type": "string"}},
        "priority": {"type": "string", "enum": ["ROUTINE","URGENT","STAT"]},
        "orderedAt": {"type": "string", "format": "date-time"},
        "collectionLocation": {"type": "string"}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 4.4 `MedicationDispensed`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EHOS MedicationDispensed",
  "type": "object",
  "required": ["eventId","eventType","eventVersion","timestamp","source","correlationId","userId","payload"],
  "properties": {
    "eventId": {"type": "string", "format": "uuid"},
    "eventType": {"const": "MedicationDispensed"},
    "eventVersion": {"const": "1"},
    "timestamp": {"type": "string", "format": "date-time"},
    "source": {"type": "string"},
    "correlationId": {"type": ["string","null"]},
    "userId": {"type": ["string","null"]},
    "payload": {
      "type": "object",
      "required": ["dispenseId","prescriptionId","patientId","medicationCode","quantity","dispensedAt","dispensedBy"],
      "properties": {
        "dispenseId": {"type": "string", "format": "uuid"},
        "prescriptionId": {"type": "string", "format": "uuid"},
        "patientId": {"type": "string", "format": "uuid"},
        "medicationCode": {"type": "string"},
        "quantity": {"type": "number"},
        "unit": {"type": "string", "enum": ["TABLET","CAPSULE","ML","MG","VIAL","PATCH"]},
        "pharmacyId": {"type": "string", "format": "uuid"},
        "dispensedAt": {"type": "string", "format": "date-time"},
        "dispensedBy": {"type": "string", "format": "uuid"}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 4.5 `InventoryUpdated`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EHOS InventoryUpdated",
  "type": "object",
  "required": ["eventId","eventType","eventVersion","timestamp","source","correlationId","userId","payload"],
  "properties": {
    "eventId": {"type": "string", "format": "uuid"},
    "eventType": {"const": "InventoryUpdated"},
    "eventVersion": {"const": "1"},
    "timestamp": {"type": "string", "format": "date-time"},
    "source": {"type": "string"},
    "correlationId": {"type": ["string","null"]},
    "userId": {"type": ["string","null"]},
    "payload": {
      "type": "object",
      "required": ["itemId","sku","delta","newLevel","reorderPoint","updatedAt","updatedBy"],
      "properties": {
        "itemId": {"type": "string", "format": "uuid"},
        "sku": {"type": "string"},
        "delta": {"type": "number"},
        "newLevel": {"type": "number"},
        "available": {"type": "number"},
        "reorderPoint": {"type": "number"},
        "location": {"type": "string"},
        "updatedAt": {"type": "string", "format": "date-time"},
        "updatedBy": {"type": "string", "format": "uuid"}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 4.6 `BillGenerated`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EHOS BillGenerated",
  "type": "object",
  "required": ["eventId","eventType","eventVersion","timestamp","source","correlationId","userId","payload"],
  "properties": {
    "eventId": {"type": "string", "format": "uuid"},
    "eventType": {"const": "BillGenerated"},
    "eventVersion": {"const": "1"},
    "timestamp": {"type": "string", "format": "date-time"},
    "source": {"type": "string"},
    "correlationId": {"type": ["string","null"]},
    "userId": {"type": ["string","null"]},
    "payload": {
      "type": "object",
      "required": ["invoiceId","patientId","billNumber","currency","totalAmount","generatedAt","status"],
      "properties": {
        "invoiceId": {"type": "string", "format": "uuid"},
        "patientId": {"type": "string", "format": "uuid"},
        "billNumber": {"type": "string"},
        "currency": {"type": "string", "minLength": 3, "maxLength": 3},
        "totalAmount": {"type": "number"},
        "lineItemCount": {"type": "integer"},
        "generatedAt": {"type": "string", "format": "date-time"},
        "status": {"type": "string", "enum": ["DRAFT","ISSUED","PAID","VOIDED","PARTIAL"]}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 4.7 `PayrollCompleted`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EHOS PayrollCompleted",
  "type": "object",
  "required": ["eventId","eventType","eventVersion","timestamp","source","correlationId","userId","payload"],
  "properties": {
    "eventId": {"type": "string", "format": "uuid"},
    "eventType": {"const": "PayrollCompleted"},
    "eventVersion": {"const": "1"},
    "timestamp": {"type": "string", "format": "date-time"},
    "source": {"type": "string"},
    "correlationId": {"type": ["string","null"]},
    "userId": {"type": ["string","null"]},
    "payload": {
      "type": "object",
      "required": ["runId","periodFrom","periodTo","employeeId","netPay","completedAt","status"],
      "properties": {
        "runId": {"type": "string", "format": "uuid"},
        "periodFrom": {"type": "string", "format": "date"},
        "periodTo": {"type": "string", "format": "date"},
        "employeeId": {"type": "string", "format": "uuid"},
        "netPay": {"type": "number"},
        "currency": {"type": "string", "minLength": 3, "maxLength": 3},
        "completedAt": {"type": "string", "format": "date-time"},
        "status": {"type": "string", "enum": ["COMPLETED","PAID","ERROR"]}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 4.8 `EmergencyTriggered`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EHOS EmergencyTriggered",
  "type": "object",
  "required": ["eventId","eventType","eventVersion","timestamp","source","correlationId","userId","payload"],
  "properties": {
    "eventId": {"type": "string", "format": "uuid"},
    "eventType": {"const": "EmergencyTriggered"},
    "eventVersion": {"const": "1"},
    "timestamp": {"type": "string", "format": "date-time"},
    "source": {"type": "string"},
    "correlationId": {"type": ["string","null"]},
    "userId": {"type": ["string","null"]},
    "payload": {
      "type": "object",
      "required": ["emergencyId","patientId","severity","triggeredAt","status"],
      "properties": {
        "emergencyId": {"type": "string", "format": "uuid"},
        "patientId": {"type": ["string","null"], "format": "uuid"},
        "severity": {"type": "string", "enum": ["LOW","MODERATE","HIGH","CRITICAL"]},
        "category": {"type": "string"},
        "location": {"type": "string"},
        "triggeredAt": {"type": "string", "format": "date-time"},
        "acknowledgedBy": {"type": ["string","null"], "format": "uuid"},
        "status": {"type": "string", "enum": ["ACTIVE","ACKNOWLEDGED","RESOLVED"]}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

---

## 5. Retry Policies

### 5.1 Principles
- **Retry transient failures only.** Permanent failures (`INVALID_SCHEMA`,
  `UNKNOWN_EVENT_TYPE`, business-rejected) go straight to the DLQ, never loop.
- **Exponential backoff with jitter** to avoid a thundering herd.
- Retry is stop-and-retry with a hard limit, then **DLQ**.
- Processing must be **idempotent** — re-processing a message yields the same
  state (per `EVENT_BUS.md` §13).

### 5.2 Retry topic model (dead-letter routing)

```
  producer
     │
     ▼
  <topic>                (main topic)
     │  consume + process
     │  transient error
     ▼
  <topic>.retry.<delay>  (retry-1s, retry-10s, retry-60s, retry-300s)
     │  attempts exhausted or permanent error
     ▼
  <topic>.dlq            (dead-letter queue)
```

On a transient failure the consumer republishes the **original envelope
unchanged** (plus retry headers) to the next retry tier instead of blocking
during a sleep — keeping consumer lag low and partitions flowing.

### 5.3 Retry policy matrix

| Event class | Max attempts | Backoff (exp + jitter) | Retry tiers | DLQ after |
|---|---|---|---|---|
| **Clinical** (PatientRegistered, AppointmentCreated, LabOrdered, MedicationDispensed, EmergencyTriggered) | 4 | 1s → 10s → 60s | `.retry.1s`, `.retry.10s`, `.retry.60s` | 4th failed attempt or permanent error |
| **Supply** (InventoryUpdated) | 4 | 1s → 10s → 60s | `.retry.1s`, `.retry.10s`, `.retry.60s` | 4th failed attempt |
| **Finance** (BillGenerated) | 5 | 1s → 10s → 60s → 300s | `.retry.1s`, `.retry.10s`, `.retry.60s`, `.retry.300s` | 5th failed attempt |
| **HR** (PayrollCompleted) | 5 | 1s → 10s → 60s → 300s | `.retry.1s`, `.retry.10s`, `.retry.60s`, `.retry.300s` | 5th failed attempt |

Retry header block on every republish:
```
X-EHOS-RetryCount
X-EHOS-RetryReason      (exception type/code, sanitized)
X-EHOS-LastAttemptAt
X-EHOS-MaxAttempts
```

---

## 6. Dead-Letter Queues

### 6.1 Configuration
| Item | Value |
|---|---|
| DLQ topic name | `<main-topic>.dlq` (e.g. `clinical.patient.registered.dlq`) |
| Retention | 60 days (investigation window per `EVENT_BUS.md` §17) |
| Replication factor | 3 |
| Partitions | same as source topic |
| Original message | never modified; headers appended only |

### 6.2 DLQ failure envelope
The DLQ record wraps the failed message:

```json
{
  "failureId": "uuid",
  "originalTopic": "clinical.patient.registered",
  "originalPartition": 2,
  "originalOffset": 10492,
  "consumedFrom": "ehos.patient.verified",
  "groupId": "ehos-verifier-01",
  "failedAt": "2026-08-16T09:14:03Z",
  "failure": {
    "code": "CONSUMER_ERROR",
    "kind": "transient|permanent",
    "message": "sanitized error message (no PHI)",
    "retryCount": 4,
    "stackDigest": "sha256"
  },
  "event": {
    "eventId": "...",
    "eventVersion": "1",
    "eventType": "PatientRegistered",
    "payload": { }
  }
}
```

`failure.code` taxonomy: `INVALID_SCHEMA`, `UNKNOWN_EVENT_TYPE`, `AUTHZ_DENIED`,
`BUSINESS_REJECTED`, `CONSUMER_ERROR`, `OUT_OF_RETRIES`.
**No PHI in failure payloads** — error strings are sanitized and truncated.

### 6.3 DLQ operations
| Operation | Mechanism |
|---|---|
| Alert | Prometheus on DLQ depth; OpsGenie for depth spikes or `OUT_OF_RETRIES` on clinical topics |
| Replay | operator tool republishes a DLQ message to the source topic with original headers (consumers are idempotent, so replay is safe) |
| Reject | reviewed and discarded after manual triage (bad event; fix upstream) |
| Audit | every DLQ entry ties back to the original `eventId` + `topic/partition/offset` |

---

## 7. Retention by Event Class

| Topic group | Retention | Rationale |
|---|---|---|
| Clinical (patient/appointment/lab/medication/emergency) | 180 days | care continuity + re-runs of alerting/agents |
| Supply (`supply.inventory.*`) | 90 days | operational + forecasting over recent history |
| Finance (`finance.billing.*`) | 7 years (or policy minimum) | audit/legal retention |
| HR (`hr.payroll.*`) | 7 years (or policy minimum) | payroll + labor compliance |
| `*.dlq` | 60 days | investigation window |
| Audit-required topics | permanent / archival | `EVENT_BUS.md` §17 |

Tiered storage moves cold segments to object storage for the long-retention
classes.

---

## 8. Event Versioning

### 8.1 Rules (never break existing consumers)
1. **Additive-only by default.** New fields must be optional or carry safe
   defaults; enums only gain values.
2. **Never rename or remove** fields, types, or enums in the same major version.
3. **Restructures** (`name` → `firstName`/`lastName`) only in a new major version
   with a supported overlap window in which both versions exist.
4. `eventVersion` lives in the envelope and is derived from the schema subject
   version; consumers branch on it when needed.
5. Old versions move to a **deprecated** state in the Schema Registry with a
   retirement date; consumers get at least 2 release cycles to migrate.

### 8.2 Schema Registry compatibility modes
| Compatibility | Used for | Example |
|---|---|---|
| `BACKWARD` | default for all topics | consumer reads new schema for old data — safe for additive-only evolution |
| `BACKWARD_TRANSITIVE` | audit topics | every prior version remains readable |
| `FORWARD` | lenient analytics topics only | old consumer reads new data |
| `NONE` | never in production | — |

### 8.3 Versioning example — `PatientRegistered` v1 → v2
**v1 (current, §4.1):** `payload.patientId`, `mrn`, `registeredAt`,
`registrationBranch`, `sourceSystem`.

**v2 (planned evolution):**
```
v2 adds (optional):  payload.gender  (string)
                     payload.consent (boolean)
v2 keeps all v1 fields unchanged, adds no required field  → BACKWARD compatible.
Subject:   clinical.patient.registered-value   (version 2)
Envelope:  "eventVersion": "2"
```

The registry verifies compatibility at registration; a producer trying a
breaking change (e.g. dropping `mrn` from `required`) is **rejected** with a
compatibility error — protecting consumers at contract time, not runtime.

**v3 (a rare breaking migration):** publish a new subject in parallel,
`clinical.patient.registered.v3-value`, when consumers opt in first:

```
+-----+   +-----+   +-----+    +-----+
| v1  |   | v2  |   | v2  |    | v3  |   ← all produced during overlap
+-----+   +-----+   +-----+    +-----+
  ▲                                ▲
 legacy consumers           new consumers (opt-in)
(no change)                 (also consume v1/v2 during the window)
```

Old subject is deprecated only after the overlap closes.

### 8.4 Producer/consumer duties
- **Producers:** register a versioned schema subject per topic; keep payloads
  additive; run the registry `BACKWARD` compatibility check before deploy.
- **Consumers:** read `eventVersion`; never crash on unknown fields; tolerate
  additive fields; migrate within the overlap window.
- **CI:** schema lint + compatibility check in every service pipeline
  (`EVENT_BUS.md` §19).

---

## 9. Operational Runbook Snippets

| Scenario | Action |
|---|---|
| Consumer repeatedly fails | stop consumer, inspect logs + `X-EHOS-RetryReason`, fix release, replay from last committed offset |
| DLQ depth growing | alert already fired; replay admissible events; reject permanently-bad events |
| Schema mutation rejected | revert; publish additive update; review registry compatibility report |
| Partition hotspot / rebalance storm | add partitions, raise `max.poll.interval`, tune `partition.assignment.strategy` |

---

## 10. Final Principle

> Every hospital action emits one reliable, versioned, retryable digital
> signal. When a signal cannot be delivered it lands, audited, in a dead-letter
> queue — never silently lost.

# END OF EVENT BUS SCHEMAS DESIGN