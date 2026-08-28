-- 0053_support_messages.sql
--
-- Telegram support bridge (phase 7): backs backend/support.py,
-- backend/services/support_bridge.py, and bot/support.py. A user's support
-- message posted from the web app (or the bot's own /support command)
-- lands in the configured admin Telegram group; an admin's reply -- sent
-- as a genuine Telegram *reply* to that exact group message -- is matched
-- back to the row via tg_message_id and surfaced to the user as an
-- in-app notification (notifications table, migration 0038).
--
-- ── Schema decision -- a new table, not app_setting ─────────────────────
-- Unlike 0044 (watchdog credentials) or 0043 (moderation), this is genuine
-- per-message data: one row per message, append-only, queried by user_id
-- and independently by tg_message_id. app_setting's key/value shape does
-- not fit a growing conversation log; the ONE scalar this feature does
-- need (the target group id, admin-editable) is seeded into app_setting
-- below, exactly the 0044 idiom.
--
-- ── direction ────────────────────────────────────────────────────────
-- 'in'  -- user -> admin group. Created by services/support_bridge.py's
--          send_to_admins(). tg_message_id is the id of the message the
--          BOT posted in the admin group -- this is the value an admin's
--          reply is matched against (see the partial index below).
-- 'out' -- admin -> user. Created by ::handle_admin_reply(). tg_message_id
--          is always NULL here: an outbound row has no Telegram message of
--          its own, it is delivered purely as an in-app notification.
--
-- ── status ───────────────────────────────────────────────────────────
-- 'sent'      -- the 'in' leg reached api.telegram.org successfully.
-- 'delivered' -- the 'out' leg's notification row was created for the user.
-- 'failed'    -- the bridge was unconfigured (support_tg_group_id / the
--                bot token empty) or the Telegram API call errored. The
--                row is kept for audit -- never dropped, and never raised
--                out of send_to_admins/handle_admin_reply: a broken bridge
--                must not break the support endpoint or the bot's reply
--                handler. See both functions' docstrings.
--
-- ── Idempotency / append-only ───────────────────────────────────────────
-- CREATE TABLE / INDEX use IF NOT EXISTS; the app_setting seed uses
-- ON CONFLICT (key) DO NOTHING (same idiom as 0044), so re-running this
-- file -- or applying it to a database where an admin already configured
-- the group -- never clears a working value back to empty. Never edit
-- this file after the session that added it; correct with 0054+.
--
-- No DO block, no dollar-quoting: migrate.py's split_sql() splits on every
-- top-level semicolon and does not understand dollar quoting (same note
-- as 0044). Every colon below is followed by a space, never an
-- identifier, so SQLAlchemy's text() cannot misread one as a bind
-- parameter -- guarded by tests/test_migration_bind_params.py.

CREATE TABLE IF NOT EXISTS support_message (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    direction     TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    body          TEXT NOT NULL,
    tg_message_id BIGINT NULL,
    status        TEXT NOT NULL DEFAULT 'sent'
                  CHECK (status IN ('sent', 'delivered', 'failed')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A user's own conversation, newest first -- the exact access pattern
-- GET /support/messages uses (WHERE user_id equals the caller ORDER BY
-- created_at DESC), same shape as conversations.py's list_conversations.
CREATE INDEX IF NOT EXISTS idx_support_message_user
    ON support_message (user_id, created_at DESC);

-- Only 'in' rows ever carry a tg_message_id (an admin's reply is matched
-- against exactly one of these); the partial WHERE clause skips every
-- 'out' row for free and keeps the index small.
CREATE INDEX IF NOT EXISTS idx_support_message_tg_id
    ON support_message (tg_message_id) WHERE tg_message_id IS NOT NULL;

-- Admin-editable target group id, same idiom as 0044's watchdog
-- credentials: seeded empty ('""' -- a JSONB string), which is the
-- explicit "unset, bridge is off" state services/support_bridge.py checks
-- for before ever calling api.telegram.org. Deliberately NOT reusing
-- watchdog_chat_id (0044): that group receives financial/security
-- anomaly alerts, a different audience and a different admin-editable
-- value from the support inbox this feature posts into.
INSERT INTO app_setting (key, value, updated_at)
VALUES ('support_tg_group_id', '""', now())
ON CONFLICT (key) DO NOTHING;
