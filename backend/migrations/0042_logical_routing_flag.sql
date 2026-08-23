-- Seed the logical_routing_enabled switch, OFF.
--
-- Phase C, step P4. services/model_resolver.py resolve_logical_model() has
-- existed and been tested since the sixth session but was called from
-- nowhere in production -- re-verified 2026-08-23 by grepping the whole
-- backend, which found the function's own definition, two references inside
-- its own docstrings, and its test file, and no call site anywhere else.
--
-- The seventh session deliberately deferred wiring it, and was right to
-- at the time. All 449 logical models were in maintenance and 1,054 of
-- 1,154 candidates were unapproved, so turning the flag on would have
-- resolved nothing and there was no way to verify the wiring live. The
-- eighth session removed that precondition with the owner's approval.
-- Measured on production 2026-08-23, twice, a minute apart, because a
-- health sweep moved the number between two earlier reads.
--   logical_model            29 available, 420 maintenance
--   logical_model_candidate  126 approved, 1,028 proposed
--
-- Default false, matching every other switch migration 0036 seeded that is
-- not already today's behaviour. OFF must be byte-for-byte identical to
-- the behaviour before this migration -- that is the phase's stated
-- acceptance criterion, not a nicety.
--
-- Safety of ON, for the record. The wiring in chat_models.py
-- _resolve_public_model() consults the logical layer ONLY when the incoming
-- model string matched nothing in model_catalog, so no model that resolves
-- today can have its route changed by this flag. Logical keys are bare
-- names (claude-sonnet-5, gemini-2-5-flash) while catalog rows are prefixed
-- (cc/claude-sonnet-5, sanjab/claude-sonnet-5), so today the two namespaces
-- do not overlap; if they ever did, the catalog wins because it is
-- consulted first. resolve_logical_model() never raises and its None means
-- "fall back to today's behaviour", so the worst case with the flag ON is
-- the behaviour with it OFF.
--
-- The registry entry in site_settings.py FLAGS is metadata only and is not
-- the source of truth for what exists in app_setting -- this row is.

INSERT INTO app_setting (key, value, updated_at)
VALUES ('logical_routing_enabled', 'false', now())
ON CONFLICT (key) DO NOTHING;
