-- 0001: Core users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE,
    password_hash TEXT,
    telegram_id INTEGER,
    phone TEXT UNIQUE,
    referral_code TEXT UNIQUE,
    referred_by INTEGER,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_referral ON users(referral_code);
