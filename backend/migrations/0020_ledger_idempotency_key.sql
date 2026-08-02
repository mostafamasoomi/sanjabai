-- The Ledger ORM model (models.py) declares idempotency_key with a unique
-- constraint, and services/billing.py::credit_wallet (plus
-- BillingService.settle()) rely on it for replay-safe ledger writes, but no
-- migration ever added the column -- 0001_baseline.sql's ledger table
-- predates it. Add it here, additive only, so the uniqueness guarantee is
-- actually enforced by the database rather than only declared in the ORM.
ALTER TABLE ledger
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_idempotency_key
    ON ledger (idempotency_key);
