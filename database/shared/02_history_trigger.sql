-- ============================================================================
-- EHOS  shared/02_history_trigger.sql
-- Generic history trigger. Applies to every business table; MUST be created
-- in every database before per-table triggers are added.
--
-- Appends one row to <table>_history on INSERT/UPDATE/DELETE of the source.
-- History tables share a fixed shape so the trigger stays generic.
-- Idempotent.
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_append_history()
RETURNS TRIGGER AS $$
DECLARE
    v_history_table text := TG_TABLE_NAME || '_history';
    v_old jsonb;
    v_new jsonb;
    v_row_id uuid;
    v_ver  int;
    v_user uuid;
    v_ref  text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_old := to_jsonb(OLD);
        v_row_id := OLD.id;
        v_ver := OLD.version;
        v_user := COALESCE(OLD.deleted_by, OLD.updated_by);
        v_ref := OLD.audit_reference;
    ELSE
        v_old := to_jsonb(OLD);
        v_new := to_jsonb(NEW);
        v_row_id := NEW.id;
        v_ver := NEW.version;
        v_user := COALESCE(NEW.updated_by, NEW.created_by);
        v_ref := NEW.audit_reference;
    END IF;

    EXECUTE format(
        'INSERT INTO %I (op, row_id, entity_version, old_row, new_row, changed_by, audit_reference) '
        || 'VALUES ($1, $2, $3, $4, $5, $6, $7)',
        v_history_table
    ) USING TG_OP, v_row_id, v_ver, v_old, v_new, v_user, v_ref;

    RETURN NULL;  -- AFTER trigger
END;
$$ LANGUAGE plpgsql;

-- DDL helper: creates the history table + trigger for a given table.
-- Usage:  SELECT ehos_make_history('<table>');
-- Requires the source table to have id, version, created_by, updated_by,
-- deleted_by, audit_reference columns (the common block).
CREATE OR REPLACE FUNCTION ehos_make_history(p_table text)
RETURNS void AS $$
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I_history ('
        || '    history_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,'
        || '    op               TEXT NOT NULL CHECK (op IN (''INSERT'',''UPDATE'',''DELETE'')),'
        || '    row_id           UUID NOT NULL,'
        || '    entity_version   INT NOT NULL,'
        || '    old_row          JSONB,'
        || '    new_row          JSONB,'
        || '    changed_by       UUID,'
        || '    changed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),'
        || '    audit_reference  TEXT'
        || ')',
        p_table
    );
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%I_history_row ON %I_history (row_id, entity_version)', p_table, p_table);
    EXECUTE format(
        'CREATE TRIGGER trg_%I_history AFTER INSERT OR UPDATE OR DELETE ON %I '
        || 'FOR EACH ROW EXECUTE FUNCTION fn_append_history()',
        p_table, p_table
    );
END;
$$ LANGUAGE plpgsql;