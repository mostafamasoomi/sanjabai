-- 0005: Wallet and reservations
CREATE TABLE IF NOT EXISTS wallet (
    user_id INTEGER NOT NULL REFERENCES users(id) PRIMARY KEY,
    balance INTEGER NOT NULL DEFAULT 0,
    reserved INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wallet_reservations (
    id SERIAL PRIMARY KEY,
    reservation_id TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'IRT',
    status TEXT NOT NULL DEFAULT 'reserved',
    model TEXT,
    price_version TEXT,
    request_id TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    reason TEXT,
    meta JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    settled_at TIMESTAMP WITHOUT TIME ZONE,
    released_at TIMESTAMP WITHOUT TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_wallet_reservations_user ON wallet_reservations(user_id);
CREATE INDEX IF NOT EXISTS idx_wallet_reservations_reservation ON wallet_reservations(reservation_id);
CREATE INDEX IF NOT EXISTS idx_wallet_reservations_idempotency ON wallet_reservations(idempotency_key);
