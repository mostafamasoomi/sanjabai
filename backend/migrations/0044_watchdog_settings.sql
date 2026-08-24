-- 0044_watchdog_settings.sql
--
-- Makes the Telegram alerting credentials admin-editable instead of
-- deploy-time-only. Until now WATCHDOG_BOT_TOKEN and WATCHDOG_CHAT_ID were
-- plain environment variables read in three places -- backend/security.py
-- (account-lockout alert), backend/watchdog.py (financial anomaly alerts,
-- read once at import as module-level constants) and
-- backend/services/moderation_store.py (content-safety alerts). Changing
-- either one meant an SSH session, an edit of .env and a container
-- restart; the owner could not do it from the panel at all.
--
-- Live check before writing this file, so the seeds below are measured and
-- not guessed -- neither variable appears in the production .env at all,
-- and the watchdog service in docker-compose.yml interpolates them with an
-- empty default. So on this host TODAY both are the empty string and every
-- one of the three alert paths short-circuits before sending. Alerting is
-- inert. Seeding both rows with the empty string therefore reproduces
-- exactly today's behaviour -- this migration is a pure no-op deploy.
--
-- ── Schema decision -- extend app_setting, do not create a table ─────────
-- Same reasoning as migration 0036, which established the pattern, and
-- 0043, which followed it. `app_setting` (key TEXT PRIMARY KEY, value JSONB
-- NOT NULL, updated_at TIMESTAMPTZ) is a generic key/value settings store
-- and already carries the six site-control flags plus the six moderation
-- settings. Two more rows, no CREATE TABLE.
--
-- ── Precedence the reader implements ────────────────────────────────────
-- backend/services/watchdog_settings.py resolves each value as
-- "non-empty DB row wins, otherwise the environment variable, otherwise
-- empty". Storing the empty string here is not a value -- it is the
-- explicit "unset, defer to the environment" state, which is also what the
-- admin panel writes when the field is cleared. That ordering is what
-- makes this deploy safe -- an operator who sets the env var today keeps
-- working unchanged, and nothing about the seeded rows can turn alerting
-- off for them.
--
-- ── SECURITY -- this row holds a bot token ──────────────────────────────
-- `watchdog_bot_token` is a live credential once an admin sets it. It is
-- stored in plaintext in app_setting, exactly like every other value in
-- that table, and this is deliberate rather than an oversight -- the value
-- must be replayable to api.telegram.org on every alert, so a one-way hash
-- (the shape api_keys uses) is not available here. The mitigation is on
-- the read side instead -- GET /admin/watchdog-settings never returns the
-- token, only "set or not" plus its last 4 characters, so the panel and
-- its network traffic never carry the secret back out. Anyone with
-- database access already has the whole wallet ledger.
--
-- ── Idempotency ─────────────────────────────────────────────────────────
-- ON CONFLICT (key) DO NOTHING on both inserts, so re-running this file --
-- or applying it to a database where an admin already stored a token
-- through the panel -- leaves the existing value untouched and never
-- clears a working credential back to empty.
--
-- No DO block and no dollar-quoting -- migrate.py's split_sql() splits on
-- every top-level semicolon and does not understand dollar quoting.
--
-- Every colon in this file is followed by a space or another colon, never
-- by an identifier, so SQLAlchemy's text() cannot misread one as a bind
-- parameter. Comments are NOT stripped before that check runs, which is
-- what made migration 0029 unrunnable. Guarded by
-- backend/tests/test_migration_bind_params.py.
--
-- APPEND-ONLY -- never edit this file after the session that added it. A
-- later correction is 0045+.

INSERT INTO app_setting (key, value, updated_at)
VALUES ('watchdog_bot_token', '""', now())
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('watchdog_chat_id', '""', now())
ON CONFLICT (key) DO NOTHING;
