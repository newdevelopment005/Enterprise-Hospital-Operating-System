-- ============================================================================
-- EHOS  notification_db/V001__init.sql
-- notification-service platform database: notification templates, outbound
-- notifications and per-channel recipients.
-- Implements DATABASE_DESIGN.md section 4.2 using global conventions 2.5
-- (common row block), 2.6 (soft delete), 2.7 (history), 2.8 (indexes) and 9
-- (event outbox). Shared files are applied first by apply.py (01_extensions,
-- 02_history_trigger, 03_outbox); fn_append_history(), ehos_make_history()
-- and outbox_events are assumed to already exist and are not recreated here.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- notification_templates
-- ---------------------------------------------------------------------------
CREATE TABLE notification_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            TEXT NOT NULL,
    channel         TEXT NOT NULL CHECK (channel IN ('EMAIL','SMS','PUSH','IN_APP')),
    locale          TEXT NOT NULL DEFAULT 'en',
    subject         TEXT,
    body            TEXT NOT NULL,
    vars_schema     JSONB,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_notification_templates_code_channel_locale
    ON notification_templates (code, channel, locale) WHERE deleted_at IS NULL;

SELECT ehos_make_history('notification_templates');

-- ---------------------------------------------------------------------------
-- notifications
-- ---------------------------------------------------------------------------
CREATE TABLE notifications (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id      UUID REFERENCES notification_templates(id),
    recipient_user_id UUID,
    recipient_email  TEXT,
    recipient_phone  TEXT,
    channel          TEXT NOT NULL,
    subject          TEXT,
    body             TEXT NOT NULL,
    payload          JSONB,
    status           TEXT NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','SENT','DELIVERED','FAILED','CANCELLED')),
    send_after       TIMESTAMPTZ,
    sent_at          TIMESTAMPTZ,
    delivered_at     TIMESTAMPTZ,
    attempts         INT NOT NULL DEFAULT 0,
    last_error       TEXT,
    provider_ref     TEXT,
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

CREATE INDEX idx_notifications_template ON notifications (template_id);
CREATE INDEX idx_notifications_status ON notifications (status, send_after);
CREATE INDEX idx_notifications_recipient ON notifications (recipient_user_id);

SELECT ehos_make_history('notifications');

-- ---------------------------------------------------------------------------
-- notification_recipients
-- ---------------------------------------------------------------------------
CREATE TABLE notification_recipients (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_id  UUID NOT NULL REFERENCES notifications(id),
    recipient_type   TEXT NOT NULL CHECK (recipient_type IN ('USER','EMAIL','PHONE','DEVICE')),
    recipient_value  TEXT NOT NULL,
    channel          TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','SENT','DELIVERED','FAILED','CANCELLED')),
    delivered_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_notification_recipients_notification ON notification_recipients (notification_id);

SELECT ehos_make_history('notification_recipients');

COMMIT;

-- ---------------------------------------------------------------------------
-- application role grants
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_notification_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_notification_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_notification_app;