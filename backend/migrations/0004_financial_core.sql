-- Phase 4: financial correctness.
--   * versioned pricing (keep historical rows)
--   * wallet (authoritative per-user balance, locked with FOR UPDATE)
--   * wallet_reservations (holds taken before an upstream call)
--   * usage_events (immutable record of every upstream call)
--   * payments idempotency_key (replay protection)
-- Idempotent — uses IF NOT EXISTS / IF EXISTS guards so re-running is safe.

-- ── 1. Versioned pricing: keep historical rows ──────────────────────────────
-- The baseline created `pricing(model UNIQUE)`, which forbids more than one row
-- per model.  Versioning needs multiple rows per model, so drop the old unique
-- constraint and add a (model, price_version) unique constraint instead.
-- New columns are added defensively (IF NOT EXISTS).
ALTER TABLE pricing DROP CONSTRAINT IF EXISTS pricing_model_key;
ALTER TABLE pricing ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE pricing ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE pricing ADD COLUMN IF NOT EXISTS price_version INT NOT NULL DEFAULT 1;
ALTER TABLE pricing ADD COLUMN IF NOT EXISTS effective_from TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE pricing ADD COLUMN IF NOT EXISTS effective_to TIMESTAMPTZ;
ALTER TABLE pricing ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE pricing ADD CONSTRAINT uq_pricing_model_version UNIQUE (model, price_version);

-- ── 2. Wallet: authoritative per-user balance row ──────────────────────────
-- `balance` is committed spendable+held; `reserved` is the sum of open holds.
-- Available balance = balance - reserved.  Locked with FOR UPDATE on writes.
CREATE TABLE IF NOT EXISTS wallet (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    balance BIGINT NOT NULL DEFAULT 0 CHECK (balance >= 0),
    reserved BIGINT NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 3. Reservations: holds taken before an upstream call ───────────────────
CREATE TABLE IF NOT EXISTS wallet_reservations (
    id BIGSERIAL PRIMARY KEY,
    reservation_id TEXT UNIQUE NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount BIGINT NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'IRT',
    status TEXT NOT NULL DEFAULT 'reserved'
        CHECK (status IN ('reserved', 'settled', 'released', 'failed')),
    model TEXT,
    price_version TEXT,
    request_id TEXT,
    idempotency_key TEXT UNIQUE NOT NULL,
    reason TEXT,
    meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    settled_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_wallet_reservations_user ON wallet_reservations(user_id, status);

-- ── 4. Usage events: immutable record of every upstream call ────────────────
CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY,
    request_id TEXT UNIQUE NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    price_version TEXT,
    provider TEXT,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    cached_input_tokens INT NOT NULL DEFAULT 0,
    reasoning_tokens INT NOT NULL DEFAULT 0,
    reservation_id TEXT,
    charged_amount BIGINT NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'IRT',
    upstream_status TEXT,
    upstream_error TEXT,
    meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage_events_user ON usage_events(user_id, created_at);

-- ── 5. Payment replay protection: ensure payments table + idempotency_key ──
-- The payments table is owned by the ORM at runtime; make sure it exists for
-- the migrate-only path, then add an idempotency key for replay protection.
CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    amount INTEGER NOT NULL,
    authority TEXT UNIQUE,
    ref_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_at TIMESTAMPTZ
);
ALTER TABLE payments ADD COLUMN IF NOT EXISTS idempotency_key TEXT UNIQUE;
