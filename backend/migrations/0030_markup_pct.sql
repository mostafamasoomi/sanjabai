-- 0030_markup_pct.sql
--
-- Owner-facing profit percentage on model prices (2026-08-22): a global
-- percentage applied to every model, plus a per-model override that wins
-- when it is set. NULL on model_catalog.markup_pct means "inherit the
-- global" -- see content.py's get_effective_markup_pct/resolve_markup_pct,
-- the single resolver every price-serving endpoint and the billing path
-- must call so the displayed and billed price for a model always agree.
--
-- The CHECK constraint rejects a negative percentage: a negative markup
-- would sell at a loss, and the product rule is that no request may ever
-- be loss-making. This is a second line of defense -- the admin API
-- (admin_catalog.py) validates the same rule before it ever reaches here.
--
-- app_setting is a small generic key/value settings table; none existed
-- before this migration. The global markup percentage is its first
-- tenant, seeded at 0 so applying this migration is a strict no-op on
-- every displayed and billed price. ON CONFLICT DO NOTHING so re-running
-- this file (or a future migration touching the same key) never resets a
-- value an admin has since changed.
--
-- No DO $$ ... $$ block is used here: migrate.py's split_sql() splits on
-- every top-level semicolon and does not understand dollar-quoting, so a
-- PL/pgSQL block with internal semicolons would be shredded into invalid
-- fragments.
--
-- Postgres has no ADD CONSTRAINT IF NOT EXISTS, and a bare ADD CONSTRAINT
-- is NOT idempotent -- verified by applying this file twice against a
-- throwaway copy of the production schema, where the second pass died with
-- `constraint "model_catalog_markup_pct_nonneg" already exists`. Relying on
-- schema_migrations to never re-run the file is not enough: it only skips
-- files that SUCCEEDED, and this statement is the last one here, so a run
-- that fails partway would leave a retry dying on this line forever.
-- DROP IF EXISTS + ADD is idempotent using only plain statements.

CREATE TABLE IF NOT EXISTS app_setting (
    key text PRIMARY KEY,
    value jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app_setting (key, value)
VALUES ('global_markup_pct', '0')
ON CONFLICT (key) DO NOTHING;

ALTER TABLE model_catalog ADD COLUMN IF NOT EXISTS markup_pct numeric;

ALTER TABLE model_catalog
    DROP CONSTRAINT IF EXISTS model_catalog_markup_pct_nonneg;

ALTER TABLE model_catalog
    ADD CONSTRAINT model_catalog_markup_pct_nonneg CHECK (markup_pct IS NULL OR markup_pct >= 0);
