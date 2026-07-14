-- 0014: Database cleanup
-- Drop redundant indexes, unused tables, and other housekeeping

-- N20: Drop redundant indexes
-- ix_api_keys_user_id duplicates idx_api_keys_user (both on api_keys.user_id)
DROP INDEX IF EXISTS ix_api_keys_user_id;

-- ix_ledger_user_id duplicates idx_ledger_user (idx_ledger_user is composite (user_id, created_at) which covers user_id alone)
DROP INDEX IF EXISTS ix_ledger_user_id;

-- idx_ledger_idempotency (non-unique) duplicates uq_ledger_idempotency (unique partial) on same column
DROP INDEX IF EXISTS idx_ledger_idempotency;

-- N41: Drop duplicate 'about' table (empty, unused; 'about_content' is the active table)
DROP TABLE IF EXISTS about;
