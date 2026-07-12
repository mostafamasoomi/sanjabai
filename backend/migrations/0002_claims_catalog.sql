-- Phase 1: claim registry + model catalog.
-- Idempotent — uses IF NOT EXISTS.

-- Claim registry: source-backed, verifiable user-facing copy.
CREATE TABLE IF NOT EXISTS claims (
    key TEXT PRIMARY KEY,
    copy_fa TEXT,
    copy_en TEXT,
    claim_type TEXT CHECK (claim_type IN ('fact','estimate','marketing','illustrative')),
    source TEXT,
    verified_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    owner TEXT,
    audience TEXT,
    feature_flag TEXT,
    fallback_copy TEXT
);

-- Model catalog: approved, versioned model + pricing contract.
CREATE TABLE IF NOT EXISTS model_catalog (
    id TEXT PRIMARY KEY,
    provider_model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    modalities JSONB NOT NULL DEFAULT '{"input":["text"],"output":["text"]}'::jsonb,
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommended_for JSONB NOT NULL DEFAULT '[]'::jsonb,
    context_window INT NOT NULL CHECK (context_window > 0),
    max_output_tokens INT CHECK (max_output_tokens IS NULL OR max_output_tokens > 0),
    currency TEXT NOT NULL DEFAULT 'IRT' CHECK (currency IN ('IRR','IRT')),
    input_per_million NUMERIC NOT NULL DEFAULT 0 CHECK (input_per_million >= 0),
    output_per_million NUMERIC NOT NULL DEFAULT 0 CHECK (output_per_million >= 0),
    cached_input_per_million NUMERIC CHECK (cached_input_per_million IS NULL OR cached_input_per_million >= 0),
    reasoning_per_million NUMERIC CHECK (reasoning_per_million IS NULL OR reasoning_per_million >= 0),
    price_version TEXT NOT NULL DEFAULT 'v1',
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    availability TEXT NOT NULL DEFAULT 'available'
        CHECK (availability IN ('available','degraded','maintenance','disabled')),
    audience JSONB NOT NULL DEFAULT '["consumer","developer"]'::jsonb,
    rate_limit JSONB,
    deprecated_at TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    provenance TEXT NOT NULL DEFAULT 'admin-approved'
        CHECK (provenance IN ('provider','admin-approved','fallback')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_model_catalog_provider ON model_catalog(provider);
CREATE INDEX IF NOT EXISTS idx_model_catalog_availability ON model_catalog(availability);
