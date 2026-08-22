-- 0034_package_entitlements.sql
--
-- GapGPT-style packages: buying a package should be able to grant a QUOTA of
-- requests and/or tokens, counted separately from Toman wallet balance.
-- Today credit_packages only ever grants Toman (credits + bonus_credits),
-- which is a different thing -- this migration adds the columns and the
-- table needed to represent an actual quota grant, without changing what
-- any existing package does.
--
-- Loss-protection rule this schema exists to enforce (see
-- backend/services/entitlements.py): a package granting "500 requests"
-- with no per-request cost ceiling is a loss path -- a user could spend all
-- 500 on the single most expensive model available and every one of those
-- requests loses money. So every entitlement carries a maximum Toman cost
-- per request (max_cost_per_request_toman); a request estimated above that
-- ceiling is not covered by the entitlement and falls through to the
-- normal wallet path instead.
--
-- ── credit_packages: four new nullable columns ──────────────────────────
-- NULL in any of these means "this package does not grant that kind of
-- quota" -- unchanged from a package's current behaviour, which grants
-- Toman only. This migration sets none of them on any existing row (see
-- the bottom of this file): what a package should actually grant is the
-- owner's decision, not something a migration can respectably guess.
--
--   request_quota                -- number of requests granted
--   token_quota                  -- number of tokens granted
--   validity_days                -- days until the grant expires; NULL = no expiry
--   max_cost_per_request_toman   -- the loss-protection ceiling
--
-- ── package_entitlement: one row per quota grant to a user ──────────────
-- requests_remaining / tokens_remaining are copied from the package's
-- quota columns at grant time and then decremented as the entitlement is
-- consumed. NULL on either means "this entitlement does not meter that
-- dimension" (e.g. a requests-only package leaves tokens_remaining NULL
-- forever) -- it does NOT mean unlimited-by-mistake, because
-- grant_entitlement() (services/entitlements.py) refuses to create a row
-- at all when a package's request_quota and token_quota are both NULL.
--
-- max_cost_per_request_toman is copied from the package at purchase time
-- (not read live from credit_packages on every request) so that editing a
-- package later can never retroactively change the ceiling a user already
-- paid for.
--
-- Idempotency: ADD COLUMN IF NOT EXISTS and CREATE TABLE/INDEX IF NOT
-- EXISTS are naturally idempotent in Postgres; this migration adds no
-- named CHECK/UNIQUE constraint, so the DROP-then-ADD dance documented in
-- 0030/0032 is not needed here.
--
-- No DO $$ ... $$ block: migrate.py's split_sql() splits on every top-level
-- semicolon and does not understand dollar-quoting, so a PL/pgSQL block
-- would be shredded into invalid fragments.
--
-- Every colon in this file is either absent from prose or part of a
-- Postgres :: cast -- never a bare colon immediately followed by an
-- identifier -- because migrate.py hands each split statement to
-- SQLAlchemy's text(), which reads that pattern as a bind parameter and
-- refuses the whole statement (comments are not stripped first; this is
-- what made migration 0029 unrunnable). Verified against
-- backend/tests/test_migration_bind_params.py.

ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS request_quota BIGINT;

ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS token_quota BIGINT;

ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS validity_days INTEGER;

ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS max_cost_per_request_toman BIGINT;

CREATE TABLE IF NOT EXISTS package_entitlement (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    package_id TEXT NOT NULL,
    requests_remaining BIGINT,
    tokens_remaining BIGINT,
    max_cost_per_request_toman BIGINT,
    expires_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT true,
    source_payment_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_package_entitlement_user_active
    ON package_entitlement(user_id, active);

CREATE INDEX IF NOT EXISTS idx_package_entitlement_expires
    ON package_entitlement(expires_at);

-- One payment may grant a package's quota exactly once, enforced by the
-- database rather than by the caller's care. handle_payment_callback()
-- already locks the payment row and rejects a replayed Zarinpal callback
-- before any grant would be reached, so this index is defence in depth --
-- but it is the same defence payment_endpoints.py already applies to the
-- Hermes order branch, which re-checks the order status even though the
-- callback lock makes that "unnecessary". Money paths in this codebase do
-- not rely on a single guard, because the caller that grants an
-- entitlement has not been written yet and cannot be reviewed today.
-- Without this, one replayed callback grants a second full quota for one
-- payment -- an uncompensated giveaway, and the loss the ceiling column
-- exists to prevent, arriving through the grant side instead.
--
-- Partial, because source_payment_id is NULL for an admin-issued grant and
-- Postgres treats NULLs in a unique index as distinct anyway. Being
-- explicit says the intent out loud: admin grants are deliberately NOT
-- deduplicated (an admin may hand the same user the same package twice on
-- purpose), payment-backed grants always are.
--
-- Keyed on (package_id, source_payment_id) rather than source_payment_id
-- alone so that a future bundle payment could still grant two DIFFERENT
-- packages, while the failure that actually threatens us -- the same
-- package granted twice for one payment -- stays blocked.
--
-- CREATE UNIQUE INDEX IF NOT EXISTS is idempotent on its own, so the
-- DROP-then-ADD dance that a named constraint needs (0030, 0032) is not
-- required here.
CREATE UNIQUE INDEX IF NOT EXISTS uq_package_entitlement_payment
    ON package_entitlement(package_id, source_payment_id)
    WHERE source_payment_id IS NOT NULL;

-- No data backfill: every existing credit_packages row (starter-credits,
-- pro-credits, business-credits) keeps all four new columns NULL, so this
-- migration is a strict no-op on current purchase/credit behaviour --
-- pricing.py::credit_package_checkout and payment_endpoints.py's callback
-- are untouched, and services/entitlements.py::grant_entitlement() is a
-- clean no-op for a package with no quota configured.
