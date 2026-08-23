-- 0041_upstream_prompt_overhead.sql
--
-- Seeds the one row backend/services/upstream_overhead.py reads:
-- app_setting.key = 'upstream_prompt_overhead'.
--
-- ── The problem this measures ──────────────────────────────────────────
-- Measured live by the coordinator on 2026-08-23. Identical two-token
-- Persian message "salam" (max_tokens=3, temperature=0), prompt_tokens
-- reported by the upstream itself for each route --
--
--   litellm    -> bynara/tencent-hy3-free           14   (clean control)
--   ninerouter -> bynara/mimo-v2.5-free             433
--   ninerouter -> gemini-api/models/gemma-4-26b     423
--   ninerouter -> cx/gpt-5.4-mini                   424
--   ninerouter -> nvidia/minimaxai/minimax-m3       571
--   ninerouter -> ag/gemini-3-flash                2422
--   ninerouter -> cc/claude-haiku-4-5-20251001     2475
--
-- Same underlying bynara model, 14 tokens through litellm and 433 through
-- ninerouter for the same two words -- the ninerouter route injects a
-- preamble the user never wrote, and today chat_billing.py bills the user
-- for all of it. Owner decision (2026-08-23) -- report it, and deduct it
-- from what the user is charged, never below the honest local estimate of
-- what they actually sent (see chat_billing.py's discount block for that
-- floor).
--
-- ── WITHDRAWN: the first cut of this migration seeded real per-prefix
-- numbers (~419-2461 per entry) computed as raw prompt_tokens minus a
-- single litellm baseline of 14. That method was wrong and was withdrawn
-- by the coordinator BEFORE this file was ever applied anywhere --
-- confirmed by a same-day follow-up measurement: the SAME model
-- (mimo-v2.5-free) reported 248 prompt_tokens on litellm and 433 on
-- ninerouter for the identical short message. litellm is NOT a uniformly
-- clean 14-token baseline -- 248 of those 248 tokens on litellm come from
-- the model's own upstream, not from any router preamble, and a single
-- global baseline of 14 would have folded that model-specific cost into
-- "9router overhead" and discounted it away. Seeding the withdrawn numbers
-- and deducting them would have undercharged every affected request below
-- its real cost -- a direct breach of "no request may be loss-making".
--
-- The corrected method (two-point, per (provider, prefix), no cross-route
-- baseline) lives in admin_overhead.py's measure() handler: send a short
-- and a long prompt to the SAME model on the SAME route, fit
-- prompt_tokens = slope * our_local_estimate + overhead, and take the
-- intercept as the overhead -- this isolates "tokens present when the
-- user wrote nothing" without assuming any other route or model is clean.
--
-- ── This migration seeds an EMPTY map, deliberately ─────────────────────
-- No entry, no provider_default, `measured_at` null. get_prompt_overhead()
-- already returns 0 for any lookup miss (its documented fail-safe value --
-- 0 means "charge the user the full amount"), so this row makes the
-- deduction feature exist and be wired up while leaving it INERT: nobody
-- is billed any differently than before this migration until an admin
-- deliberately runs POST /admin/upstream-overhead/measure and it writes
-- real, derived numbers with their own p1/p2/c1/c2/slope/sample_model
-- recorded alongside each one for auditability. Shipping a deduction that
-- defaults to off and must be measured on, rather than shipping a guess,
-- is the honest default here.
--
-- ── Schema decision: app_setting, not a new table ──────────────────────
-- Same reasoning as 0036/0039 -- app_setting (key TEXT PRIMARY KEY, value
-- JSONB NOT NULL, updated_at) is the generic settings store this project
-- already has; a dedicated table next to it would repeat the
-- credit_packages mistake this codebase is on record about. This
-- migration inserts exactly one row, ON CONFLICT DO NOTHING, so it never
-- clobbers a value an admin re-measure already wrote via
-- POST /admin/upstream-overhead/measure.
--
-- ── Idempotency / bind-param safety ─────────────────────────────────────
-- ON CONFLICT (key) DO NOTHING, matching 0036/0039/0042. Every colon in
-- this file, comments included, is followed by a space or a JSON value,
-- never directly by a letter, so none of them can be misread by
-- SQLAlchemy text() as a bind parameter -- see
-- backend/tests/test_migration_bind_params.py. No DO $$ block, no ADD
-- CONSTRAINT IF NOT EXISTS -- append-only and idempotent per project
-- convention.

INSERT INTO app_setting (key, value, updated_at)
VALUES (
    'upstream_prompt_overhead',
    '{
        "version": 1,
        "measured_at": null,
        "entries": {},
        "provider_default": {}
    }'::jsonb,
    now()
)
ON CONFLICT (key) DO NOTHING;
