-- Create the `notifications` table declared by models.py's Notification ORM
-- model (models.py line 282) but never backed by any migration -- the
-- fourth instance of this exact drift class, after 0033 (proxy_config),
-- 0035 (four missing tables) and 0037 (thirteen columns on plans and
-- credit_packages). Measured 2026-08-22: `SELECT to_regclass
-- ('public.notifications')` on production returns null, and grepping every
-- file in this directory for the word "notifications" finds nothing.
--
-- backend/notifications.py serves GET /notifications and POST
-- /notifications/{nid}/read against this table (registered in app.py).
-- Impact is bigger than those two routes: hermes.py does
-- `session.add(Notification(...))` inside larger server-provisioning and
-- suspension transactions (around lines 737, 897 and 904 there), so the
-- missing table has been silently rolling back whole hermes commits, not
-- only 500-ing the notifications endpoints. Anonymous callers hit a 401
-- before ever reaching the query, and the frontend does not currently call
-- /notifications, so the direct endpoint-level user impact has been low --
-- the hermes transaction coupling is the part that actually mattered.
--
-- Columns and the index below match models.py's Notification class exactly
-- (id, user_id with index=True, type, title, body, read, created_at).
-- Idempotent: CREATE TABLE / CREATE INDEX both use IF NOT EXISTS, matching
-- the style of every other migration in this directory.

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    type TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
