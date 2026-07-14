-- 0004: About content, proxy config, conversations, payments
CREATE TABLE IF NOT EXISTS about_content (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'درباره ما',
    body TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS proxy_config (
    id SERIAL PRIMARY KEY,
    proxy_url TEXT NOT NULL DEFAULT '',
    proxy_type TEXT NOT NULL DEFAULT 'socks5',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL DEFAULT 'گفتگوی جدید',
    model TEXT NOT NULL DEFAULT '',
    messages JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    amount INTEGER NOT NULL,
    authority TEXT NOT NULL UNIQUE,
    ref_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    payment_type TEXT NOT NULL DEFAULT 'wallet_topup',
    reference_id TEXT,
    idempotency_key TEXT UNIQUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMP WITHOUT TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_authority ON payments(authority);
CREATE INDEX IF NOT EXISTS idx_payments_idempotency ON payments(idempotency_key);
