-- 0006: Usage events, notifications, API keys, audit logs
CREATE TABLE IF NOT EXISTS usage_events (
    id SERIAL PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    model TEXT NOT NULL,
    price_version TEXT,
    provider TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    reservation_id TEXT,
    charged_amount INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'IRT',
    upstream_status TEXT,
    upstream_error TEXT,
    meta JSONB,
    billing_source TEXT NOT NULL DEFAULT 'wallet',
    subscription_id INTEGER,
    credits_charged INTEGER NOT NULL DEFAULT 0,
    payg_charged INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_usage_events_user ON usage_events(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_request ON usage_events(request_id);

CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);

CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL DEFAULT 'Default',
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL DEFAULT 'sk-',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_used TIMESTAMP WITHOUT TIME ZONE,
    scopes TEXT NOT NULL DEFAULT 'read',
    expires_at TIMESTAMP WITHOUT TIME ZONE,
    revoked_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    admin_user_id INTEGER,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    details JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
