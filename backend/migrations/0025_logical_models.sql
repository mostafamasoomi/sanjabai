-- 0025_logical_models.sql
-- Phase 6: one user-visible logical model, N physical upstream candidates.
-- Additive only. Nothing reads these tables until LOGICAL_ROUTING_ENABLED=true.

CREATE TABLE IF NOT EXISTS logical_model (
    key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT,
    vendor TEXT,
    context_window INT,
    max_output_tokens INT,
    currency TEXT NOT NULL DEFAULT 'IRT'
        CHECK (currency IN ('IRR','IRT')),
    input_per_million BIGINT NOT NULL DEFAULT 0,
    output_per_million BIGINT NOT NULL DEFAULT 0,
    cached_input_per_million BIGINT,
    usd_input_per_million NUMERIC(14,6),
    usd_output_per_million NUMERIC(14,6),
    availability TEXT NOT NULL DEFAULT 'maintenance'
        CHECK (availability IN ('available','degraded','maintenance','disabled')),
    routing_policy TEXT NOT NULL DEFAULT 'cheapest_healthy'
        CHECK (routing_policy IN ('cheapest_healthy','priority','pinned')),
    pinned_candidate_id TEXT REFERENCES model_catalog(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS logical_model_candidate (
    id BIGSERIAL PRIMARY KEY,
    logical_key TEXT NOT NULL REFERENCES logical_model(key) ON DELETE CASCADE,
    catalog_id TEXT NOT NULL REFERENCES model_catalog(id) ON DELETE CASCADE,
    priority INT NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT true,
    state TEXT NOT NULL DEFAULT 'proposed'
        CHECK (state IN ('proposed','approved','rejected')),
    est_cost_usd_input NUMERIC(14,6),
    est_cost_usd_output NUMERIC(14,6),
    added_by TEXT NOT NULL DEFAULT 'clusterer',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (logical_key, catalog_id)
);

CREATE INDEX IF NOT EXISTS idx_lmc_route
    ON logical_model_candidate (logical_key, enabled, priority)
    WHERE state = 'approved';
CREATE INDEX IF NOT EXISTS idx_lmc_catalog ON logical_model_candidate (catalog_id);
