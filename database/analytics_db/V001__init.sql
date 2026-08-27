-- ============================================================================
-- EHOS  analytics_db  V001__init.sql
-- analytics-service: department metrics, daily metric points, localization
-- overrides, seed state (read-model warehouse, no service-local writes).
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- department_metrics — current KPI snapshot for one department metric
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS department_metrics (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    department  VARCHAR(50) NOT NULL,
    metric_key  VARCHAR(80) NOT NULL,
    label       VARCHAR(120) NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    unit        VARCHAR(20) NOT NULL,
    delta_pct   DOUBLE PRECISION NOT NULL DEFAULT 0,
    good_when   VARCHAR(10) NOT NULL DEFAULT 'up',
    status      VARCHAR(10) NOT NULL DEFAULT 'ok',
    hint        VARCHAR(255),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_department_metric ON department_metrics (department, metric_key);

-- ----------------------------------------------------------------------------
-- metric_points — daily history point for a department metric series
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metric_points (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    department VARCHAR(50) NOT NULL,
    metric_key VARCHAR(80) NOT NULL,
    day        DATE NOT NULL,
    value      DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metric_points_series ON metric_points (department, metric_key);
CREATE INDEX IF NOT EXISTS idx_metric_points_day ON metric_points (day);

-- ----------------------------------------------------------------------------
-- localization_overrides — per-country overrides managed by administrators
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS localization_overrides (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country_code VARCHAR(2) NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    timezone     VARCHAR(64) NOT NULL,
    locale_tag   VARCHAR(20) NOT NULL,
    exchange_rate DOUBLE PRECISION NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_localization_country UNIQUE (country_code)
);

-- ----------------------------------------------------------------------------
-- seed_state — whether the realistic demo/ops dataset has been seeded
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seed_state (
    id        BIGSERIAL PRIMARY KEY,
    seed_key  VARCHAR(50) NOT NULL,
    seeded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_seed_key UNIQUE (seed_key)
);

-- ----------------------------------------------------------------------------
-- grants
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_analytics_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_analytics_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_analytics_app;

COMMIT;