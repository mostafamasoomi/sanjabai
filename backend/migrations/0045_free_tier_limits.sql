-- 0045_free_tier_limits.sql
--
-- Redefines the free tier for a user who has never paid and holds no
-- package and no wallet balance. The old shape was a per-model message
-- bucket (services/free_tier.py, 5 messages then 50 per model per 5 hours).
-- The owner's decision replaces it with three combined limits, all owned
-- by the free tier and all admin-tunable:
--
--   1. free_hourly_limit               -- messages per rolling hour (3)
--   2. free_lifetime_limit             -- messages EVER, a hard paywall (30)
--   3. free_tier_max_input_per_million -- the "cheap models only" ceiling:
--        a free user may only send to a model whose base input price is at
--        or below this many Toman per million tokens. The free tier is free
--        (the platform absorbs the model cost up to the limits above), so a
--        free user must not be able to spend that giveaway on an expensive
--        model. 60000 Toman/M sits at the top of the flash-lite-and-below
--        cluster in today's catalog (~11 models) and below every mid/premium
--        model. It is a starting value, not a law -- the admin panel
--        (backend/admin_free_tier.py, GET/POST /admin/free-tier-settings)
--        edits all three live.
--
-- ── The lifetime counter is a real column, not a Redis key ──────────────
-- free_lifetime_limit is a hard paywall: once a user has spent their 30
-- free messages they stay blocked until they pay. That fact must survive a
-- Redis eviction/flush, so it lives in a durable column on users, not in
-- Redis (the hourly window, which resets anyway, stays in Redis). Default 0
-- so every existing user starts with their full free allowance -- there is
-- one real user today (the owner) and they hold a balance, so they are
-- exempt from the free tier entirely and this column never gates them.
--
-- ── Storage for the three numbers: app_setting ──────────────────────────
-- Same key/value JSONB store (key TEXT PRIMARY KEY, value JSONB NOT NULL,
-- updated_at TIMESTAMPTZ) that migrations 0036/0043/0044 extend. The values
-- are JSON numbers, read by services/free_tier_config.py with a 60s cache
-- and a safe hardcoded fallback (3 / 30 / 60000) if a row is missing or
-- unreadable, so the gate keeps working even before this migration is
-- applied.
--
-- ── Idempotency ─────────────────────────────────────────────────────────
-- ADD COLUMN IF NOT EXISTS (house style, see 0032) and ON CONFLICT DO
-- NOTHING on every insert, so re-running this file, or applying it to a
-- database where an admin has already changed a value through the panel,
-- changes nothing.
--
-- No DO block, no dollar-quoting -- migrate.py's split_sql() splits on
-- every top-level semicolon. Every colon in this file is followed by a
-- space or is inside prose, never immediately before an identifier, so
-- SQLAlchemy's text() cannot misread one as a bind parameter (comments are
-- NOT stripped before that check -- migration 0029's lesson).
--
-- APPEND-ONLY -- never edit after the session that added it; a later
-- correction is 0046+.

ALTER TABLE users ADD COLUMN IF NOT EXISTS free_messages_used BIGINT NOT NULL DEFAULT 0;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('free_hourly_limit', '3', now())
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('free_lifetime_limit', '30', now())
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('free_tier_max_input_per_million', '60000', now())
ON CONFLICT (key) DO NOTHING;
