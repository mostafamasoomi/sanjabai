-- 0007: Plans, credit packages, billing settings, user memories
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    name_fa TEXT NOT NULL,
    name_en TEXT NOT NULL,
    price_monthly INTEGER NOT NULL DEFAULT 0,
    monthly_token_quota INTEGER NOT NULL DEFAULT 0,
    daily_token_limit INTEGER NOT NULL DEFAULT 0,
    models_allowed JSONB DEFAULT '[]',
    priority_queue BOOLEAN NOT NULL DEFAULT FALSE,
    features JSONB DEFAULT '[]',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS credit_packages (
    id TEXT PRIMARY KEY,
    name_fa TEXT NOT NULL,
    name_en TEXT NOT NULL,
    base_amount INTEGER NOT NULL DEFAULT 0,
    bonus_percent INTEGER NOT NULL DEFAULT 0,
    total_credits INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_billing_settings (
    user_id INTEGER NOT NULL REFERENCES users(id) PRIMARY KEY,
    payg_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    payg_hard_limit INTEGER,
    notify_on_usage_pct INTEGER NOT NULL DEFAULT 80,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_memories (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    source TEXT NOT NULL DEFAULT 'manual',
    tags TEXT[],
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_memories_user ON user_memories(user_id);
