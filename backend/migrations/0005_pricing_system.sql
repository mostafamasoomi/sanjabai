-- Phase 5: pricing system — extend existing tables.
-- Tables (plans, credit_packages, user_billing_settings) were created
-- directly via psql. This migration only extends existing tables.
-- Idempotent — uses IF NOT EXISTS guards.

-- ── 4. Extend subscriptions table ──────────────────────────────────────────
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_id TEXT REFERENCES plans(id);
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS monthly_token_quota BIGINT NOT NULL DEFAULT 0;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS tokens_used_this_period BIGINT NOT NULL DEFAULT 0;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS price_paid BIGINT NOT NULL DEFAULT 0;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_active
    ON subscriptions(user_id, status) WHERE status = 'active';

-- ── 5. Extend usage_events table ───────────────────────────────────────────
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS billing_source TEXT;
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS subscription_id BIGINT;
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS credits_charged BIGINT NOT NULL DEFAULT 0;
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS payg_charged BIGINT NOT NULL DEFAULT 0;

-- ── 6. Extend payments table ───────────────────────────────────────────────
ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_type TEXT NOT NULL DEFAULT 'wallet_topup';
ALTER TABLE payments ADD COLUMN IF NOT EXISTS reference_id TEXT;
