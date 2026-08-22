-- 0033_proxy_config_columns.sql
--
-- Fixes a live 500 on GET /org/default-model (content.py) and every
-- /admin/proxy* route (admin.py): the ORM model ProxyConfig (models.py)
-- declares proxy_type, active and default_model, but the baseline table
-- (migrations/0001_baseline.sql) only ever created id, proxy_url and
-- updated_at. Any SELECT that goes through ProxyConfig.__table__.select()
-- asks Postgres for all five ORM columns and dies with:
--
--   column proxy_config.proxy_type does not exist
--
-- The Next.js proxy in front of the API swallows that 500 and returns 200
-- with an empty body, which is why this went unnoticed.
--
-- Defaults below are chosen to match the ORM's own Mapped[...] defaults
-- (models.py) exactly, so a pre-existing row (id=1, proxy_url already set
-- by an admin) backfills to the same values a freshly-inserted ORM row
-- would have gotten, rather than some other guessed default.
--
-- Idempotency: ADD COLUMN IF NOT EXISTS is naturally idempotent in
-- Postgres, so no DROP-then-ADD dance is needed here (that pattern is only
-- required for constraints, which this migration does not add).
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

ALTER TABLE proxy_config ADD COLUMN IF NOT EXISTS proxy_type TEXT NOT NULL DEFAULT 'socks5';

ALTER TABLE proxy_config ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE proxy_config ADD COLUMN IF NOT EXISTS default_model TEXT NOT NULL DEFAULT '';
