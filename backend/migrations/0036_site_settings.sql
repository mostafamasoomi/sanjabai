-- 0036_site_settings.sql
--
-- The gap this closes: the admin panel has no runtime "turn a section off"
-- switch anywhere. Every real kill switch in this codebase today
-- (TASK_SCHEDULER_ENABLED, OPENROUTER_ENABLED, and the not-yet-wired
-- LOGICAL_ROUTING_ENABLED) is an environment variable, so flipping one
-- needs an SSH session and a container restart -- the owner cannot do it
-- from the panel. The roadmap's Phase B acceptance test is literally "an
-- admin turns a section off", and that does not exist yet.
--
-- ── Schema decision: extend app_setting, do not create a new table ────────
-- `app_setting` already exists (`key TEXT PRIMARY KEY, value JSONB NOT
-- NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`) and already holds
-- exactly one row (`global_markup_pct`). It is a generic key/value settings
-- store, not something specific to markup -- nothing about its shape ties
-- it to that one row. This project already has two admin UIs writing
-- `credit_packages` on record as technical debt; inventing a second
-- settings table next to a settings table that already does the job would
-- be the same mistake again. So this migration adds no CREATE TABLE at
-- all -- it only inserts new rows (one per flag) into the table that
-- already exists.
--
-- ── The flags, and why each default reproduces TODAY's behaviour ─────────
-- A migration that silently turns a feature off in production is worse
-- than the gap it closes, so every seed below was checked against the
-- live container before being written here (see the session's report for
-- the exact commands), not guessed:
--
--   maintenance_mode           default false -- brand new capability, no
--                               code path reads it yet, so there is no
--                               "current behaviour" to preserve beyond
--                               "the site stays up" -- false is the only
--                               value consistent with that.
--   signups_enabled             default true  -- signup has no such gate
--                               today (backend/auth.py signup()), so
--                               "enabled" is what already happens.
--   chat_enabled                 default true  -- backend/chat.py's
--                               /v1/chat/completions has no such gate
--                               today, so "enabled" is what already
--                               happens.
--   image_generation_enabled     default true  -- backend/images.py's
--                               /v1/images/generations has no such gate
--                               today (it is separately blocked per-model
--                               by model_catalog.availability, which this
--                               flag does not touch or replace).
--   task_scheduler_enabled       default false -- mirrors the live value of
--                               the TASK_SCHEDULER_ENABLED env var, read
--                               directly from the running sanjabai_api
--                               container (unset, and
--                               services/task_scheduler.py's _env_flag
--                               defaults an unset flag to false).
--   openrouter_enabled           default false -- mirrors the live value of
--                               the OPENROUTER_ENABLED env var, same
--                               container check (unset -> providers.py's
--                               _env_flag also defaults to false).
--
-- These two env-mirroring rows are DATA ONLY in this migration -- the env
-- vars in providers.py / services/task_scheduler.py are left untouched and
-- keep governing actual behaviour until a follow-up change deliberately
-- wires the DB flag in (see the session report for the exact call sites).
-- Until that wiring lands, an admin flipping these two specific switches in
-- the panel changes a stored value but not yet the live behaviour -- the
-- panel must label them as such.
--
-- ── Idempotency ────────────────────────────────────────────────────────
-- `app_setting` already exists, so there is no CREATE TABLE to make
-- idempotent. Every INSERT below uses ON CONFLICT (key) DO NOTHING, so
-- running this file twice (or applying it to a database that already has
-- one of these keys, however that key got there) never overwrites a value
-- someone already set -- it simply leaves existing rows untouched.
--
-- No DO $$ ... $$ block: migrate.py's split_sql() splits on every
-- top-level semicolon and does not understand dollar-quoting, so a
-- PL/pgSQL block would be shredded into invalid fragments.
--
-- Every colon in this file is followed by a space, not an identifier, so
-- none of them can be misread as a SQLAlchemy text() bind parameter --
-- comments are not stripped before that check runs, which is what made
-- migration 0029 unrunnable. Verified against
-- backend/tests/test_migration_bind_params.py.

INSERT INTO app_setting (key, value, updated_at)
VALUES ('maintenance_mode', 'false', now())
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('signups_enabled', 'true', now())
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('chat_enabled', 'true', now())
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('image_generation_enabled', 'true', now())
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('task_scheduler_enabled', 'false', now())
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('openrouter_enabled', 'false', now())
ON CONFLICT (key) DO NOTHING;
