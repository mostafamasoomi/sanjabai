-- Second-round reconciliation of wallet.balance with the ledger's running
-- balance (see 0017_wallet_ledger_reconciliation.sql for the first pass).
--
-- 0017 fixed chat usage debits (chat.py::_record_usage) to update
-- wallet.balance in the same transaction as their ledger row, and
-- backfilled the drift that had accumulated up to that point. But three
-- other ledger-writing paths kept the same bug alive afterward:
-- wallet.py's /wallet/topup, auth.py's referral-signup bonus, and
-- hermes.py's monthly server-renewal charge all only ever appended a
-- Ledger row computed from SUM(ledger), never touching wallet.balance
-- itself. Any user who topped up, received a referral bonus, or had a
-- Hermes server renewed since 0017 ran now has wallet.balance drifted
-- from the ledger. The code fix alongside this migration
-- (services/billing.py::credit_wallet now locks + updates wallet.balance,
-- and topup/referral/hermes now route through it or an equivalent locked
-- debit) keeps them in sync going forward; this reconciles the drift
-- accumulated in the meantime.
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

INSERT INTO wallet (user_id, balance, reserved)
SELECT l.user_id, GREATEST(SUM(l.amount), 0), 0
FROM ledger l
LEFT JOIN wallet w ON w.user_id = l.user_id
WHERE w.user_id IS NULL
GROUP BY l.user_id;
