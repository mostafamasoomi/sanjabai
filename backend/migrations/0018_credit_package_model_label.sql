-- Let a credit package be labeled with a specific model, so it can be sold
-- as "N million tokens of <model> for <price>" (Bynara-style token
-- packages) instead of only a generic Toman top-up bundle.
--
-- Deliberately additive only: the existing base_amount/bonus_percent/
-- total_credits fields and the checkout flow (services/billing.py,
-- pricing.py::credit_package_checkout, payment.py::handle_payment_callback)
-- are untouched. A model-labeled package still charges and credits
-- total_credits 1:1 today, same as an unlabeled one -- model_id is display
-- metadata (which model the bundle is framed around, for computing an
-- "approx N tokens" estimate client-side from that model's live price), not
-- a new pricing mechanism. NULL means "generic credit", unchanged from
-- before this migration.
ALTER TABLE credit_packages
    ADD COLUMN IF NOT EXISTS model_id TEXT REFERENCES model_catalog(id) ON DELETE SET NULL;
