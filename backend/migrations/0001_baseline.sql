-- Phase 0 baseline: core tables for Multiai.
-- Idempotent — uses IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT UNIQUE,
    password_hash TEXT,
    telegram_id BIGINT UNIQUE,
    phone TEXT UNIQUE,
    referral_code TEXT UNIQUE,
    referred_by BIGINT REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    name TEXT,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_hash ON sessions(token_hash);

CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    plan TEXT NOT NULL CHECK (plan IN ('free','basic','pro')),
    starts_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ends_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ledger (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    txn_type TEXT NOT NULL,
    amount BIGINT NOT NULL CHECK (amount <> 0),
    balance_after BIGINT NOT NULL CHECK (balance_after >= 0),
    reason TEXT NOT NULL,
    ref_type TEXT,
    ref_id TEXT,
    meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger(user_id, created_at);

CREATE TABLE IF NOT EXISTS payment_orders (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    amount_irr BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','completed','failed')),
    authority TEXT,
    ref_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_orders_authority
    ON payment_orders(authority) WHERE authority IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_orders_ref_id
    ON payment_orders(ref_id) WHERE ref_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS quota (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    model_alias_id BIGINT,
    daily_limit INT NOT NULL DEFAULT 200000,
    used_today INT NOT NULL DEFAULT 0,
    reset_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_aliases (
    id BIGSERIAL PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    priority INT NOT NULL DEFAULT 0,
    enabled BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS pricing (
    id BIGSERIAL PRIMARY KEY,
    model TEXT UNIQUE NOT NULL,
    input_per_million INT NOT NULL DEFAULT 0,
    output_per_million INT NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'IRT',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS features (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    order_idx INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS discounts (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    order_idx INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS about (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    title TEXT,
    body TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS proxy_config (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    proxy_url TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    admin_user_id BIGINT,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);