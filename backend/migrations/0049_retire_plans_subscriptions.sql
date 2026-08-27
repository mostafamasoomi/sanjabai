-- 0049_retire_plans_subscriptions.sql
--
-- WHY
-- Sanjabai sold two different things that meant the same thing: a monthly
-- `plan` (subscriptions table) and a pre-paid `credit_package`. Only the
-- second was ever finished -- /subscribe wrote a Subscription row whose
-- quota nothing enforced, while every actual gate in the product
-- (services/user_quota.py, services/premium_quota.py,
-- services/entitlements.py) reads credit_packages and package_entitlement.
-- The owner decided (session 23) to retire the plan/subscription concept
-- entirely: `credit_packages` is the ONLY product concept from here on.
--
-- Measured immediately before this migration was written:
--     plans = 3, subscriptions = 0, credit_packages = 3,
--     payments WHERE payment_type='subscription' = 0 (none pending).
-- Nobody holds a subscription and no gateway payment ever completed against
-- one, so this drop destroys no customer entitlement. That is exactly why
-- it is being done now rather than later.
--
-- A pg_dump of all three tables was taken and verified non-empty before
-- this file was applied (backups/pre-0049-plans-merge-*.sql). The dump is
-- the archive; no zombie table is kept behind for "just in case" -- a table
-- nothing writes to is a table that quietly rots into a wrong answer.
--
-- ── Part 1: credit_packages loses four dead columns ─────────────────────
--   name, price, credits, bonus_credits
--
-- These are the pre-rename originals of name_fa/name_en, base_amount and
-- total_credits. Nothing has read them since migration 0018: the ORM
-- (backend/models/_billing.py::CreditPackage) never mapped them, checkout
-- charges base_amount and credits total_credits, and every admin read goes
-- through the new names. They survived only because all four are NOT NULL
-- with no default, which forced backend/admin_packages.py to invent filler
-- values on every INSERT (`cleaned.setdefault('bonus_credits', 0)` and
-- friends) and forced backend/admin_packages_validation.py to carry a
-- `_LEGACY_MONEY_FIELDS` special case that refuses NULL for them. Dropping
-- the columns is what lets both of those disappear -- the filler existed
-- to satisfy the constraint, not to record anything.
--
-- IF EXISTS on each drop: house idiom (see 0032/0034/0045/0046), so
-- re-running this file is a no-op.
--
-- ── Part 2: subscriptions, then plans ───────────────────────────────────
-- Order is forced by the foreign key subscriptions.plan_id -> plans.id
-- (confirmed live in pg_constraint before writing this). Dropping plans
-- first would fail. There is no third dependant: no view and no other FK
-- references either table.
--
-- usage_events.subscription_id is DELIBERATELY LEFT IN PLACE. It carries no
-- foreign key (checked), it is nullable, every existing row holds NULL, and
-- it is the only trace historical usage rows have of the concept. Dropping
-- it would rewrite history to say something that was true was never
-- recorded. It is dead weight, not a lie, so it stays.
--
-- Historical rows in `payments` with payment_type='subscription' are
-- likewise untouched -- there are none today, but the payments table is the
-- financial record and is never rewritten by a schema change.
--
-- ⚠ The money trap this migration creates, closed in the same change:
-- backend/payment_endpoints.py's callback used to branch on
-- payment_type='subscription' to grant the subscription. With that branch
-- removed, a stale pending callback carrying that payment_type would fall
-- through to handle_payment_callback's DEFAULT behaviour, which is to
-- credit the wallet with the charged amount -- silently gifting money for a
-- product that no longer exists. An early 410 guard in payment_endpoints.py
-- returns before any credit path is reached. Do not remove that guard while
-- old `payments` rows with this payment_type exist.
--
-- ── Invariants this migration must not break ────────────────────────────
-- credit_packages.request_quota and max_cost_per_request_toman stay NULL on
-- every row. Setting either is how a package accidentally hands out free
-- requests (see migration 0046's header). This file touches neither.
--
-- No DO block, no dollar-quoting -- migrate.py's split_sql() splits on every
-- top-level semicolon. Every colon here is followed by a space or sits in
-- prose, never immediately before an identifier, so SQLAlchemy's text()
-- cannot misread one as a bind parameter (migration 0029's lesson; comments
-- are NOT stripped before that check).
--
-- APPEND-ONLY -- never edit after the session that added it; a later
-- correction is 0050+.

ALTER TABLE credit_packages DROP COLUMN IF EXISTS name;

ALTER TABLE credit_packages DROP COLUMN IF EXISTS price;

ALTER TABLE credit_packages DROP COLUMN IF EXISTS credits;

ALTER TABLE credit_packages DROP COLUMN IF EXISTS bonus_credits;

DROP TABLE IF EXISTS subscriptions;

DROP TABLE IF EXISTS plans;
