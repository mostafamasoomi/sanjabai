-- 0012_blocker_fixes.sql — Performance indexes and constraints
-- Blockers #5-9, #12-13, #18-19

-- Conversations: fast user+updated_at lookups for sidebar
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
    ON conversations(user_id, updated_at DESC);

-- Audit logs: fast time-range and action-type queries
CREATE INDEX IF NOT EXISTS idx_audit_logs_created
    ON audit_logs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action
    ON audit_logs(action);

-- Quota: fast per-user lookups
CREATE INDEX IF NOT EXISTS idx_quota_user
    ON quota(user_id);

-- Ledger: referential integrity
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_ledger_user'
    ) THEN
        ALTER TABLE ledger
            ADD CONSTRAINT fk_ledger_user
            FOREIGN KEY (user_id) REFERENCES users(id);
    END IF;
END$$;
