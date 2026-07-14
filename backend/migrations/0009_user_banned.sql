-- Add banned column to users table.
-- Idempotent — uses IF NOT EXISTS guard.

ALTER TABLE users ADD COLUMN IF NOT EXISTS banned BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned);
