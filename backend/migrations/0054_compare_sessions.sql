-- 0054_compare_sessions.sql
--
-- Compare history + continue (docs/superpowers/specs/2026-08-30-compare-
-- history-continue-design.md). /v1/compare (backend/chat_compare.py) was
-- fully stateless -- one prompt in, two model answers out, nothing
-- persisted. This table gives a user a history of past comparisons they
-- can reopen and continue, either broadcasting one message to both models
-- at once or sending to only one side without touching the other.
--
-- Same shape convention as `conversations` (0001_baseline.sql) -- a JSON
-- blob per side, no separate messages table, since neither `conversations`
-- nor `scheduled_tasks` needed one and the same one-row-per-session /
-- JSONB-column-of-{role,content}-dicts pattern applies here unchanged.
--
-- thread_a / thread_b are independent, undeduplicated arrays -- after a
-- solo message to side A, A and B threads simply diverge from that point.
-- No shared-prefix pointer; the data volume is trivial (same as any chat
-- conversation) and a pointer scheme adds a failure mode for no real
-- saving.
--
-- model_a / model_b hold the canonical provider_model_id used for routing
-- and billing (never shown to a normal user -- see content.py's
-- no-provider-leak rule); model_a_requested / model_b_requested hold
-- exactly what the user picked, echoed back on every response, same
-- distinction /v1/compare already draws for its own response shape.
--
-- ── Idempotency / append-only ───────────────────────────────────────────
-- CREATE TABLE / INDEX use IF NOT EXISTS so re-running this file is a
-- no-op. Never edit this file after the session that added it; correct
-- with 0055+.
--
-- No DO block, no dollar-quoting: migrate.py's split_sql() splits on every
-- top-level semicolon and does not understand dollar quoting (same note as
-- 0044/0053). Every colon below is followed by a space or a letter that is
-- NOT part of a bind-param-looking token -- guarded by
-- tests/test_migration_bind_params.py.

CREATE TABLE IF NOT EXISTS compare_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    model_a TEXT NOT NULL,             -- canonical provider_model_id
    model_b TEXT NOT NULL,
    model_a_requested TEXT NOT NULL,   -- what the user picked; echoed back,
    model_b_requested TEXT NOT NULL,   -- never the resolved provider id
    title TEXT NOT NULL DEFAULT '',
    thread_a JSONB NOT NULL DEFAULT '[]',
    thread_b JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-- A user's own comparison history, newest first -- the exact access
-- pattern GET /v1/compare/sessions uses (WHERE user_id equals the caller
-- ORDER BY updated_at DESC), same shape as conversations.py's
-- list_conversations / 0053's idx_support_message_user.
CREATE INDEX IF NOT EXISTS idx_compare_sessions_user
    ON compare_sessions (user_id, updated_at DESC);
