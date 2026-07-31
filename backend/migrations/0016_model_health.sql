-- Model health tracking.
--
-- Two tables on purpose:
--
--   model_health_event  append-only samples, one row per probe or per real
--                       request. Cheap to write from the hot chat path.
--   model_health_state  the current rollup per model. The status page, the
--                       catalog and the "is this model usable" check all read
--                       this, so none of them has to aggregate the event table
--                       on every request.
--
-- Before this, `model_catalog.availability` was only ever set by hand and the
-- frontend carried its own hard-coded list of "working" model ids, so both
-- drifted from reality the moment an upstream changed.

CREATE TABLE IF NOT EXISTS model_health_event (
    id BIGSERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown',
    -- 'probe'   synthetic max_tokens=1 request from the health loop
    -- 'traffic' outcome of a real user request
    source TEXT NOT NULL CHECK (source IN ('probe', 'traffic')),
    ok BOOLEAN NOT NULL,
    latency_ms INT,
    -- Short reason code only (e.g. 'timeout', 'http_502'). Never a response
    -- body: these rows are read by an unauthenticated status page.
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The rollup query is always "recent events for a model", newest first.
CREATE INDEX IF NOT EXISTS idx_model_health_event_model_time
    ON model_health_event (model_id, created_at DESC);
-- Used by the retention sweep.
CREATE INDEX IF NOT EXISTS idx_model_health_event_time
    ON model_health_event (created_at);

CREATE TABLE IF NOT EXISTS model_health_state (
    model_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'unknown'
        CHECK (status IN ('healthy', 'degraded', 'down', 'unknown')),
    -- Rolling window statistics, recomputed by the health loop.
    success_rate DOUBLE PRECISION,
    latency_p50_ms INT,
    latency_p95_ms INT,
    sample_count INT NOT NULL DEFAULT 0,
    consecutive_failures INT NOT NULL DEFAULT 0,
    last_ok_at TIMESTAMPTZ,
    last_error TEXT,
    last_error_at TIMESTAMPTZ,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_model_health_state_status
    ON model_health_state (status);

-- Which upstream a catalog entry came from, so discovery can tell an entry it
-- created apart from one an admin curated, and so health can be attributed.
ALTER TABLE model_catalog ADD COLUMN IF NOT EXISTS upstream TEXT;
