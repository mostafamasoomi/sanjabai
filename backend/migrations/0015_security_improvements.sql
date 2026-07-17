-- 0015_security_improvements.sql
-- Account lockout tracking, enhanced audit trail, TOTP MFA skeleton

-- Enhanced audit trail: add IP and user-agent columns
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS ip_address TEXT;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_agent TEXT;

-- Admin MFA: TOTP secret on users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret TEXT;

-- Index for faster audit log queries
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_target ON audit_logs (target_type, target_id);
