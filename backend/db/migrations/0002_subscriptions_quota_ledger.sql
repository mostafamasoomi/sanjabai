-- 0002: Subscriptions, quotas, ledger
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    plan VARCHAR(32) NOT NULL,
    starts_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    ends_at TIMESTAMP WITHOUT TIME ZONE,
    status TEXT NOT NULL DEFAULT 'active',
    monthly_token_quota INTEGER NOT NULL DEFAULT 0,
    tokens_used_this_period INTEGER NOT NULL DEFAULT 0,
    auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
    cancelled_at TIMESTAMP WITHOUT TIME ZONE,
    price_paid INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);

CREATE TABLE IF NOT EXISTS quota (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    daily_limit INTEGER NOT NULL,
    used_today INTEGER NOT NULL DEFAULT 0,
    reset_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_quota_user ON quota(user_id);

CREATE TABLE IF NOT EXISTS ledger (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    reason TEXT NOT NULL,
    meta JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger(user_id);
