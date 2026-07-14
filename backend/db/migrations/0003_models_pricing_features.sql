-- 0003: Model aliases, pricing, features, discounts
CREATE TABLE IF NOT EXISTS model_aliases (
    id SERIAL PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_model_aliases_key ON model_aliases(key);

CREATE TABLE IF NOT EXISTS pricing (
    id SERIAL PRIMARY KEY,
    model TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown',
    input_per_million INTEGER NOT NULL DEFAULT 0,
    output_per_million INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'IRT',
    source TEXT,
    price_version INTEGER NOT NULL DEFAULT 1,
    effective_from TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    effective_to TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pricing_model_version UNIQUE (model, price_version)
);
CREATE INDEX IF NOT EXISTS idx_pricing_model ON pricing(model);

CREATE TABLE IF NOT EXISTS features (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT 'star',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    order_idx INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS discounts (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    percent INTEGER NOT NULL DEFAULT 10,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMP WITHOUT TIME ZONE,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
