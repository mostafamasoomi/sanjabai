-- Reconcile wallet.balance with the ledger's real running balance.
--
-- Root cause being fixed alongside this migration (see chat.py::_record_usage):
-- real chat usage was only ever recorded as a Ledger row — it never touched
-- wallet.balance. wallet.balance was written to only by top-ups
-- (services.billing.credit_wallet) and by BillingService.settle(), which was
-- defined but never called from any production code path. So wallet.balance
-- stayed frozen at whatever a user last topped up, forever, while the
-- pre-flight balance check in BillingService.reserve() gates on
-- `wallet.balance - wallet.reserved` — meaning it never reflected real spend,
-- and any user who fully spent their topped-up ledger balance could keep
-- chatting for free indefinitely afterward. This is the exact drift
-- backend/watchdog.py's `wallet_ledger_mismatch` CRITICAL rule already
-- monitors for.
--
-- The ledger is the historically-accurate record (every real debit/credit
-- was correctly appended there), so it is the source of truth here: bring
-- wallet.balance in line with it once, then the code fix (which now debits
-- wallet.balance in the same transaction as every ledger charge) keeps them
-- in sync going forward.
--
-- Idempotent: safe to re-run (recomputes the same SUM every time).

UPDATE wallet w
SET balance = GREATEST(COALESCE((
    SELECT SUM(l.amount) FROM ledger l WHERE l.user_id = w.user_id
), 0), 0),
    updated_at = now()
WHERE w.balance <> GREATEST(COALESCE((
    SELECT SUM(l.amount) FROM ledger l WHERE l.user_id = w.user_id
), 0), 0);

-- Create wallet rows for any user with ledger history but no wallet row yet
-- (shouldn't normally happen — every ledger-writing path creates the wallet
-- first — but guard against it defensively).
INSERT INTO wallet (user_id, balance, reserved)
SELECT l.user_id, GREATEST(SUM(l.amount), 0), 0
FROM ledger l
LEFT JOIN wallet w ON w.user_id = l.user_id
WHERE w.user_id IS NULL
GROUP BY l.user_id;

-- Clear any reservation holds left over from a crash mid-request (a hold
-- that never reached release()/settle() before a process restart). Safe to
-- do at migration time: this runs during API startup, before any traffic is
-- served, so there is no genuinely in-flight reservation to disturb.
UPDATE wallet_reservations
SET status = 'released', released_at = now()
WHERE status = 'reserved';

UPDATE wallet
SET reserved = 0, updated_at = now()
WHERE reserved <> 0;
