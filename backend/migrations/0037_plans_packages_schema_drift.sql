-- Codify the undocumented drift on `plans` and `credit_packages`.
--
-- WHAT THIS FIXES
-- Both tables carry columns that the running code reads and writes every
-- day, and that NO migration in this repository ever creates. They exist on
-- production only because someone once added them by hand through psql.
-- Measured on 2026-08-22 by grepping every file in this directory --
-- these seven columns on `plans`
--     name_fa, name_en, monthly_token_quota, daily_token_limit,
--     models_allowed, priority_queue, sort_order
-- and these six on `credit_packages`
--     name_fa, name_en, base_amount, bonus_percent, total_credits,
--     sort_order
-- appear in zero migration files, while backend/models.py's Plan and
-- CreditPackage declare every one of them and backend/admin.py,
-- backend/pricing.py and backend/admin_packages.py all query them.
--
-- The consequence is that this repository could NOT rebuild its own
-- database. A fresh environment gets `plans` and `credit_packages` from
-- 0004_financial_core_part2.sql with only their original columns, and the
-- first ORM query or admin write against either one dies on an
-- UndefinedColumn. Production works purely because of hand-run DDL that
-- was never written down.
--
-- Note that 0023_schema_drift_fix.sql LOOKS like it addresses this and does
-- not. Its `CREATE TABLE IF NOT EXISTS plans` describes a different table
-- entirely (a `price_irt INTEGER`, no quota column) and is a silent no-op
-- because 0004 already created the table. Reading 0023 gives a false sense
-- that these tables are covered; they are not.
--
-- This is the same class of bug as 0033 (proxy_config, three missing
-- columns, /org/default-model returning 500) and 0035 (four tables the ORM
-- described and the database never had, which took the whole assistants
-- section down for every user). Third occurrence, so it is a pattern rather
-- than an accident -- tests/test_schema_drift.py is extended in the same
-- change to cover Plan and CreditPackage so a fourth cannot ship silently.
--
-- EFFECT ON PRODUCTION
-- None. Every statement below is ADD COLUMN IF NOT EXISTS and every one of
-- these columns already exists on production with exactly the type given
-- here (types copied from a live `\d plans` / `\d credit_packages`). This
-- migration only changes what a FRESH database looks like. It writes no
-- data and drops nothing.
--
-- Nullability deliberately matches production exactly rather than being
-- "improved" -- adding NOT NULL where production has NULL would make a
-- fresh database diverge from the real one in a new direction, which is the
-- problem this file exists to end.

-- plans
ALTER TABLE plans ADD COLUMN IF NOT EXISTS name_fa TEXT;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS name_en TEXT;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS monthly_token_quota BIGINT;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS daily_token_limit BIGINT DEFAULT 0;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS models_allowed JSONB DEFAULT '[]'::jsonb;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS priority_queue BOOLEAN DEFAULT false;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;

-- credit_packages
ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS name_fa TEXT;
ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS name_en TEXT;
ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS base_amount BIGINT;
ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS bonus_percent INTEGER DEFAULT 0;
ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS total_credits BIGINT;
ALTER TABLE credit_packages ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;
