-- ============================================================================
-- EHOS  scheduling_db / V001__init.sql
-- Service: appointment-service + queue-service
-- Description: Baseline schema for the scheduling database: appointments
--   (with projections of cross-db patient/provider/department refs), provider
--   schedules, generated schedule_slots, and the queues / queue_entries flow.
--   Per-table history triggers included.
-- Design: DATABASE_DESIGN.md sections 2, 5.2, 9, 10.
-- Requires: shared 01_extensions.sql (pgcrypto, pg_trgm), 02_history_trigger.sql
--   (fn_append_history(), ehos_make_history()), 03_outbox.sql (outbox_events)
--   applied first by apply.py. No \i includes in this file.
-- Postgres 16+, lowercase snake_case, app role: ehos_scheduling_app.
-- ============================================================================

BEGIN;

CREATE TABLE appointments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID NOT NULL,                 -- cross-db ref to patient-service (no FK)
    patient_snapshot    JSONB,
    provider_id         UUID,
    department_id       UUID,
    appointment_type    TEXT NOT NULL,
    start_time          TIMESTAMPTZ NOT NULL,
    end_time            TIMESTAMPTZ,
    duration_min        INT,
    status              TEXT NOT NULL DEFAULT 'SCHEDULED'
                        CHECK (status IN ('SCHEDULED','ARRIVED','IN_PROGRESS','COMPLETED','CANCELLED','NO_SHOW','REQUESTED','RESCHEDULED')),
    reason              TEXT,
    priority            TEXT NOT NULL DEFAULT 'ROUTINE' CHECK (priority IN ('ROUTINE','URGENT','EMERGENCY')),
    source              TEXT DEFAULT 'MANUAL' CHECK (source IN ('MANUAL','PORTAL','CALL','KIOSK','AI')),
    consultation_room   TEXT,
    cancellation_reason TEXT,
    cancelled_by        UUID,
    cancelled_at        TIMESTAMPTZ,
    reschedule_source   UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by          UUID,
    updated_by          UUID,
    version             INT NOT NULL DEFAULT 1,
    audit_reference     TEXT,
    deleted_at          TIMESTAMPTZ,
    deleted_by          UUID,
    deletion_reason     TEXT
);

CREATE INDEX idx_appointments_patient_status ON appointments (patient_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_appointments_provider_time ON appointments (provider_id, start_time) WHERE deleted_at IS NULL;
CREATE INDEX idx_appointments_department_time ON appointments (department_id, start_time) WHERE deleted_at IS NULL;

SELECT ehos_make_history('appointments');

CREATE TABLE schedules (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id   UUID NOT NULL,
    department_id UUID,
    slot_type     TEXT NOT NULL CHECK (slot_type IN ('CLINIC','SURGERY','ROUNDS','TELEHEALTH')),
    recur_rule    TEXT,
    starts_on     DATE NOT NULL,
    ends_on       DATE,
    weekdays      SMALLINT[],
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    status        TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_schedules_provider ON schedules (provider_id, starts_on);

SELECT ehos_make_history('schedules');

CREATE TABLE schedule_slots (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schedule_id    UUID NOT NULL REFERENCES schedules(id),
    slot_start     TIMESTAMPTZ NOT NULL,
    slot_end       TIMESTAMPTZ NOT NULL,
    status         TEXT NOT NULL DEFAULT 'FREE' CHECK (status IN ('FREE','BLOCKED','BOOKED','CANCELLED')),
    appointment_id UUID,                 -- cross-db appt ref (no FK)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by     UUID,
    updated_by     UUID,
    version        INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_schedule_slots_schedule_start
    ON schedule_slots (schedule_id, slot_start)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_schedule_slots_schedule ON schedule_slots (schedule_id);
CREATE INDEX idx_schedule_slots_time ON schedule_slots (status, slot_start);

SELECT ehos_make_history('schedule_slots');

CREATE TABLE queues (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_type    TEXT NOT NULL CHECK (queue_type IN ('OUTPATIENT','EMERGENCY','LAB','PHARMACY','ADMISSION','RADIOLOGY')),
    department_id UUID,
    name          TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    status        TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);

SELECT ehos_make_history('queues');

CREATE TABLE queue_entries (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_id         UUID NOT NULL REFERENCES queues(id),
    patient_id       UUID NOT NULL,
    patient_snapshot JSONB,
    ticket_number    TEXT NOT NULL,
    priority         INT NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'WAITING'
                     CHECK (status IN ('WAITING','CALLED','IN_PROGRESS','COMPLETED','SKIPPED','CANCELLED')),
    joined_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    called_at        TIMESTAMPTZ,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    served_by        UUID,
    wait_time_min    INT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE UNIQUE INDEX uq_queue_entries_queue_ticket
    ON queue_entries (queue_id, ticket_number)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_queue_entries_queue ON queue_entries (queue_id, status, priority);

SELECT ehos_make_history('queue_entries');

GRANT USAGE ON SCHEMA public TO ehos_scheduling_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_scheduling_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_scheduling_app;

COMMIT;