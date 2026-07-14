-- 0013: Add missing FK constraints and indexes
-- Adds referential integrity for columns that reference other tables
-- but were never constrained at the database level.

-- audit_logs.admin_user_id -> users.id
ALTER TABLE audit_logs
    ADD CONSTRAINT IF NOT EXISTS fk_audit_admin
    FOREIGN KEY (admin_user_id) REFERENCES users(id);

-- usage_events.subscription_id -> subscriptions.id
ALTER TABLE usage_events
    ADD CONSTRAINT IF NOT EXISTS fk_usage_sub
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id);

-- ledger.user_id -> users.id
ALTER TABLE ledger
    ADD CONSTRAINT IF NOT EXISTS fk_ledger_user
    FOREIGN KEY (user_id) REFERENCES users(id);
