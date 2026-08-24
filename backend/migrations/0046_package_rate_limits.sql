-- 0046_package_rate_limits.sql
--
-- credit_packages.request_quota is read by two unrelated consumers that mean
-- different things by it:
--
--   1. services/user_quota.py read it LIVE as a rate limit (messages per
--      rolling 5-hour window, all models combined).
--   2. services/entitlements.py::grant_entitlement copies it at purchase
--      time into package_entitlement.requests_remaining -- a finite bundle
--      of free requests that bypasses the wallet entirely (chat_billing.py
--      sets cost = 0 and returns before the wallet is touched).
--
-- So setting request_quota to get a rate limit also handed the buyer that
-- many free requests. The owner does not want to give anything away. This
-- migration gives the rate limit its own columns, completely independent of
-- entitlements/request_quota.
--
-- ── credit_packages: two new nullable columns ───────────────────────────
--   rate_limit_per_window          -- messages per 5-hour window, all
--                                      models combined. NULL = this package
--                                      grants no rate-limit tier (unchanged
--                                      from today: services/user_quota.py's
--                                      package tier simply does not apply).
--   premium_rate_limit_per_window  -- of those messages, how many may land
--                                      on an "expensive" model (see below).
--                                      NULL = no premium sub-allowance, i.e.
--                                      services/premium_quota.py exempts a
--                                      user holding only this column NULL.
--
-- Both are read live from credit_packages by services/user_quota.py and
-- services/premium_quota.py, the same live-not-snapshotted rule
-- request_quota already followed for the rate limit -- this is a refreshing
-- cap that must follow the admin's current setting, unlike an entitlement
-- grant, which is snapshotted on purchase and never re-read.
--
-- ── app_setting: premium_model_min_input_per_million ────────────────────
-- The Toman-per-million-input-tokens ceiling services/premium_quota.py uses
-- to decide whether a model counts against premium_rate_limit_per_window --
-- a model whose BASE input price is strictly greater than this value is
-- "expensive". Compared against the base price, never the marked-up price
-- (same reasoning services/free_tier.py applies to its own cheap-model
-- ceiling): a served price varies with global_markup_pct, and if the
-- premium check compared that instead, raising the global markup would
-- silently reclassify ordinary models as premium without the owner touching
-- this setting. Same key/value JSONB store (key TEXT PRIMARY KEY, value
-- JSONB NOT NULL, updated_at TIMESTAMPTZ) migrations 0036/0043/0044/0045
-- extend, and the same ON CONFLICT DO NOTHING seed idiom as migration 0045.
-- 150000 is a starting value, not a law -- it sits above today's mid-tier
-- cluster and is intended to bracket only the genuinely premium models.
--
-- ── Idempotency ───────────────────────────────────────────────────────────
-- ADD COLUMN IF NOT EXISTS (house style, see 0032/0034/0045) and ON CONFLICT
-- DO NOTHING on the insert, so re-running this file, or applying it after an
-- admin has already changed the setting through a future panel, changes
-- nothing.
--
-- No DO block, no dollar-quoting -- migrate.py's split_sql() splits on every
-- top-level semicolon. Every colon in this file is followed by a space or is
-- inside prose, never immediately before an identifier, so SQLAlchemy's
-- text() cannot misread one as a bind parameter (comments are NOT stripped
-- before that check -- migration 0029's lesson).
--
-- Leaving both new columns and the new setting at their NULL/default values
-- is a strict no-op on today's behaviour: services/user_quota.py's rate
-- limit reads rate_limit_per_window instead of request_quota starting with
-- this session, and every existing package has request_quota NULL, so the
-- rate-limit tier stays exempt for every current package exactly as before;
-- services/premium_quota.py exempts any user without a package whose
-- premium_rate_limit_per_window is set, which is every package today.
--
-- APPEND-ONLY -- never edit after the session that added it; a later
-- correction is 0047+.

ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS rate_limit_per_window BIGINT;

ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS premium_rate_limit_per_window BIGINT;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('premium_model_min_input_per_million', '150000', now())
ON CONFLICT (key) DO NOTHING;
