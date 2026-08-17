-- 0023_schema_drift_fix.sql
-- Fixes schema drift by ensuring tables created ad-hoc (via psql or legacy code)
-- have proper migrations, using IF NOT EXISTS to avoid breaking existing DBs.

-- Subscriptions plans
CREATE TABLE IF NOT EXISTS plans (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    price_irt INTEGER NOT NULL,
    features JSONB DEFAULT '[]'::jsonb,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

-- Credit packages
CREATE TABLE IF NOT EXISTS credit_packages (
    id VARCHAR(64) PRIMARY KEY,
    name_fa VARCHAR(128),
    name_en VARCHAR(128),
    base_amount INTEGER NOT NULL,
    bonus_percent INTEGER DEFAULT 0,
    total_credits INTEGER NOT NULL,
    model_id VARCHAR(128),
    active BOOLEAN DEFAULT true,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

-- Conversations (in case it wasn't migrated from some old state)
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(255) DEFAULT '',
    model VARCHAR(128),
    messages JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);
