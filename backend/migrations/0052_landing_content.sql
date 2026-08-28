-- 0052_landing_content.sql
--
-- B-LAND phase 6. Makes the landing page editable from the admin panel,
-- without moving its content off the frontend. Today all landing copy
-- lives in thirteen static TypeScript modules under
-- frontend/components/landing/content/ (api, capabilities, catalog,
-- comparison, constants, faq, features, footer, hero, nav, pricing, stats,
-- steps). That stays true after this migration -- this table never holds
-- the landing page's actual content, only an OVERRIDE per module, read by
-- backend/landing_content.py's public GET /landing/content and written by
-- backend/admin_landing.py's admin endpoints.
--
-- ── Antifragile by construction ─────────────────────────────────────────
-- This migration seeds NOTHING. An empty table is not a degraded state --
-- it is the intended default, meaning "every one of the thirteen modules
-- renders exactly as its static file says". A row only exists once an
-- admin has explicitly overridden that one module through the panel. If
-- Postgres or this table is ever unreachable, the read side fails open to
-- the same "no overrides" answer (see landing_content.py), so a broken
-- override store degrades the site to precisely today's behaviour, never
-- past it.
--
-- ── Why one row per module, not one row per field ───────────────────────
-- `key` is one of the thirteen module names above (enforced in Python by
-- landing_content.ALLOWED_KEYS, not by a CHECK constraint here, so adding
-- a fourteenth module later is a one-line Python change and not a new
-- migration). `value` holds that module's whole override payload as one
-- JSONB document. A wide, ungoverned key/value table inviting arbitrary
-- string keys is exactly what this schema avoids -- thirteen rows, never
-- more, each one a known, reviewable unit.
--
-- ── updated_by is nullable on purpose ────────────────────────────────────
-- This backend's admin auth (dependencies.admin_required) is a single
-- shared admin session or header token, not per-admin-user identity --
-- there is no numeric admin user id anywhere else in this schema to store
-- here. The column exists for the day that changes; until then every write
-- leaves it NULL, same spirit as the nullable actor columns elsewhere in
-- this codebase's audit trail.
--
-- ── Idempotency ──────────────────────────────────────────────────────────
-- CREATE TABLE IF NOT EXISTS, no seed INSERTs to guard with ON CONFLICT
-- (there is nothing to seed) -- re-running this file, or applying it to a
-- database where an admin has already stored overrides through the panel,
-- changes nothing.
--
-- No DO block, no dollar-quoting -- migrate.py's split_sql() splits on
-- every top-level semicolon and does not understand dollar quoting.
--
-- Every colon in this file is followed by a space, never directly by an
-- identifier, so SQLAlchemy's text() cannot misread one as a bind
-- parameter -- comments are NOT stripped before that check runs (the
-- lesson from migration 0029). Guarded by
-- backend/tests/test_migration_bind_params.py.
--
-- APPEND-ONLY -- never edit this file after the session that added it. A
-- later correction is 0053+.

CREATE TABLE IF NOT EXISTS landing_content (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by  INTEGER NULL
);
