-- 0051_referral_rewards.sql
--
-- Owner decision, recorded 2026-08-28: a referral reward is never paid at
-- signup. It is paid on the invitee's FIRST successful payment, and only
-- then. This migration is the storage for that decision; the payout logic
-- itself lives in services/referral.py (phase 5, backend half).
--
-- ── Why signup-time payout is refused, on the record ─────────────────────
-- This server has no email-verification column at all (models/_users.py --
-- there is no `verified` field to gate on). The signup rate limiter's key
-- is `sha256(ip + user-agent)` (security.py:106-126), which a rotated
-- User-Agent defeats trivially. The disposable-email blocklist covers four
-- domains (security.py:306). Crediting a wallet the moment an account is
-- created, under those three facts, is free money for anyone who can write
-- a loop that varies a header. Gating on a real, external, costly event --
-- the invitee actually paying Zarinpal -- is the only payout trigger that
-- can't be farmed by a script alone.
--
-- ── Schema: a new table, not another app_setting-shaped hack ─────────────
-- Unlike the free-tier limits (0045) or the watchdog settings (0044), this
-- is not three admin-tunable scalars -- it is one row PER (inviter,
-- invitee) pair with its own lifecycle (pending -> paid, or pending ->
-- capped, or left pending forever if the invitee never pays), so it gets
-- its own table. The three admin-tunable NUMBERS that control payout
-- amounts and the per-inviter cap still go in app_setting, exactly like
-- 0045, because those really are just three scalars an admin edits live
-- (see services/referral.py, backend/admin_referral.py).
--
-- `invitee_id` is UNIQUE: a user is invited at most once, ever, no matter
-- how many referral links they click -- the first attribution recorded
-- (auth.py's signup handler) wins and every later one is a silent
-- ON CONFLICT (invitee_id) DO NOTHING no-op. This is also what makes a
-- second `settle_on_first_payment` call for the same invitee safe: there
-- is only ever one row to find, and once it is 'paid' it is no longer
-- 'pending', so a replayed payment callback finds nothing to settle.
--
-- `status` transitions, enforced by the CHECK constraint, never by
-- convention alone:
--   pending  -- attribution recorded at signup, no money has moved yet.
--   paid     -- the invitee's first successful payment triggered payout;
--               inviter_amount_toman/invitee_amount_toman/paid_at are the
--               amounts and time that ACTUALLY landed (copied from
--               app_setting at settle time, not read live afterwards, so a
--               later admin edit to the reward amount never rewrites
--               history the way editing a package's price should not
--               rewrite an entitlement someone already spent -- see
--               0034's docstring for the same reasoning applied there).
--   capped   -- the invitee paid, but the inviter had already reached
--               referral_reward_cap paid referrals; attribution is kept
--               for the record but nothing was credited.
--   void     -- reserved for a future admin action (e.g. fraud reversal);
--               nothing in this phase writes it, but the CHECK constraint
--               allows for it now so a later migration does not have to
--               touch this constraint again.
--
-- ── Money-safe seed: every amount seeded at ZERO ─────────────────────────
-- referral_reward_toman and referral_invitee_reward_toman seed at 0, not
-- some plausible-looking number. Deploying this migration's CODE must not,
-- by itself, move a single Toman -- turning the feature on is a deliberate
-- later admin action (PUT /admin/referral/settings), the same separation
-- 0045 drew between "the gate exists" and "the gate is strict". At 0/0,
-- services/referral.py's settle_on_first_payment() reads both amounts as
-- zero, treats the feature as off, and leaves every pending row untouched
-- -- see that module's docstring for the exact fail-safe check.
-- referral_reward_cap seeds at 10 (a cap value, not a money value -- it
-- only ever LIMITS a payout that is already zero at this amount, so it
-- carries no financial risk on its own).
--
-- ── Idempotency ────────────────────────────────────────────────────────
-- CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS, and ON CONFLICT
-- DO NOTHING on every app_setting insert (house style, see 0045/0050) --
-- re-running this file, or applying it after an admin already edited a
-- value through the panel, changes nothing.
--
-- No DO block, no dollar-quoting -- migrate.py's split_sql() splits on
-- every top-level semicolon (0045's lesson, restated here because this
-- file also touches app_setting). Every colon below is followed by a
-- space or is inside prose, never immediately before an identifier.
--
-- APPEND-ONLY -- never edit after the session that added it; a later
-- correction is 0052+.

CREATE TABLE IF NOT EXISTS referral_reward (
    id                    SERIAL PRIMARY KEY,
    inviter_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    invitee_id            INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    status                TEXT NOT NULL DEFAULT 'pending',
    inviter_amount_toman  INTEGER NOT NULL DEFAULT 0,
    invitee_amount_toman  INTEGER NOT NULL DEFAULT 0,
    paid_at               TIMESTAMPTZ NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT referral_reward_status_check
        CHECK (status IN ('pending', 'paid', 'capped', 'void'))
);

CREATE INDEX IF NOT EXISTS idx_referral_reward_inviter_status
    ON referral_reward (inviter_id, status);

INSERT INTO app_setting (key, value, updated_at)
VALUES ('referral_reward_toman', '0', now())
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('referral_invitee_reward_toman', '0', now())
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_setting (key, value, updated_at)
VALUES ('referral_reward_cap', '10', now())
ON CONFLICT (key) DO NOTHING;
