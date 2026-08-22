-- 0032_image_pricing.sql
--
-- Per-image pricing for model_catalog, backing POST /v1/images/generations
-- (backend/images.py). image_price_per_unit is the BASE Toman price for one
-- generated image, before the profit percentage (model_catalog.markup_pct /
-- app_setting.global_markup_pct, migration 0030) is applied at read/bill
-- time via content.apply_markup -- the same composition rule token pricing
-- already follows.
--
-- NULL means "no price has been set for this model, and it therefore
-- cannot be served" -- images.py's gate 2 refuses any request for a model
-- with a NULL image_price_per_unit with a hard 400, never a guessed or
-- fallback rate. This migration sets no prices for any row (see below);
-- pricing every media model is the owner's decision, not something this
-- migration can respectably guess given that no successful image
-- generation has ever been observed (scripts/probe_media.py) -- there is no
-- real cost to price against yet.
--
-- This migration does not touch model_catalog.availability. Every image
-- model is 'maintenance' today (no upstream credential works), and adding a
-- price column has no bearing on that; the availability gate in images.py
-- runs BEFORE the price gate and independently refuses every request until
-- the owner both fixes credentials AND sets a price.
--
-- Idempotency: Postgres has no ADD CONSTRAINT IF NOT EXISTS, and a bare ADD
-- CONSTRAINT is NOT idempotent -- migrations/0030_markup_pct.sql documents
-- this exact failure mode (re-running the file dies with `constraint ...
-- already exists`) and is the house style followed here: DROP CONSTRAINT IF
-- EXISTS, then ADD, using only plain statements.
--
-- No DO $$ ... $$ block: migrate.py's split_sql() splits on every top-level
-- semicolon and does not understand dollar-quoting, so a PL/pgSQL block
-- would be shredded into invalid fragments.
--
-- Every colon in this file is either absent from prose or part of a `::`
-- cast -- never a bare colon immediately followed by an identifier --
-- because migrate.py hands each split statement to SQLAlchemy's text(),
-- which reads that pattern as a bind parameter and refuses the whole
-- statement (comments are not stripped first; this is what made 0029
-- unrunnable). Verified against backend/tests/test_migration_bind_params.py.

ALTER TABLE model_catalog ADD COLUMN IF NOT EXISTS image_price_per_unit numeric;

ALTER TABLE model_catalog
    DROP CONSTRAINT IF EXISTS model_catalog_image_price_per_unit_nonneg;

ALTER TABLE model_catalog
    ADD CONSTRAINT model_catalog_image_price_per_unit_nonneg
        CHECK (image_price_per_unit IS NULL OR image_price_per_unit >= 0);
