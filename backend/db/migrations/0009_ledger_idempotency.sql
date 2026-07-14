-- PHASE-6 fix: ledger.idempotency_key exists in the ORM (app.py Ledger model)
-- but was never added to the live table. Backend analytics + idempotent
-- billing reads/writes this column, so the missing column 500s /admin/analytics.
-- Add it (nullable + partial unique index so multiple NULLs are allowed).

ALTER TABLE ledger ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

-- Unique only where the key is actually set (Postgres allows many NULLs).
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_idempotency
    ON ledger (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ledger_idempotency
    ON ledger (idempotency_key);
