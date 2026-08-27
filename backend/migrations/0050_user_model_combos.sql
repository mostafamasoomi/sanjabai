-- 0050_user_model_combos.sql
--
-- Phase 4 (Smart v2). Two things: user-defined model combos, and the OFF
-- switch for the LLM router that Phase 4 introduces.
--
-- ── Why combos store a public_id, never a provider route ────────────────
--
-- `user_model_combo_item.model_public_id` holds the SAME string the user
-- sees in the picker (`sanjab/...`), not `model_catalog.provider_model_id`.
-- Three reasons, in order of how expensive getting this wrong would be:
--
--   1. Product rule: a normal user never sees a provider or a route. If the
--      column held `ag/gpt-oss-120b-medium`, every read path that echoes a
--      combo back to its owner would leak one.
--   2. A public_id is stable across re-routing. When an admin re-points a
--      public_id at a different upstream (which model_discovery.py does on
--      its own), a combo built on the route silently starts referring to a
--      model the user never chose. Built on the public_id, it keeps meaning
--      what the user picked.
--   3. `chat.py::_resolve_public_model` already canonicalizes public_id ->
--      provider_model_id exactly once, as early as possible, on every chat
--      path. Storing the public form means combos join that existing funnel
--      instead of opening a second, unaudited one.
--
-- Deliberately NOT a foreign key to model_catalog(public_id): a model can be
-- withdrawn (public_id set NULL, or the row retired) while a user's combo
-- still names it. An FK would either block the withdrawal or cascade-delete
-- somebody's saved combo behind their back. services/smart_router.py
-- resolves each item at selection time and skips what no longer resolves --
-- an unresolvable item is a dead entry, not a broken combo.
--
-- ── Why no ON DELETE for the user ──────────────────────────────────────
--
-- `user_id` cascades: a deleted user's combos are theirs and go with them.
-- `combo_id` cascades: items have no meaning without their combo.
--
-- ── The flag ───────────────────────────────────────────────────────────
--
-- `smart_llm_router_enabled` follows 0042's idiom exactly: the app_setting
-- row is the source of truth, the site_settings.py FLAGS entry is metadata
-- describing where it is read. Default FALSE -- the router costs a real
-- (small) model call per request, so it does not switch itself on.

CREATE TABLE IF NOT EXISTS user_model_combo (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    policy      TEXT NOT NULL DEFAULT 'sequential',
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT user_model_combo_policy_check
        CHECK (policy IN ('sequential', 'round_robin')),
    CONSTRAINT user_model_combo_name_len_check
        CHECK (char_length(name) BETWEEN 1 AND 60),
    CONSTRAINT user_model_combo_user_name_uniq UNIQUE (user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_user_model_combo_user
    ON user_model_combo (user_id);

CREATE TABLE IF NOT EXISTS user_model_combo_item (
    id               SERIAL PRIMARY KEY,
    combo_id         INTEGER NOT NULL
                     REFERENCES user_model_combo(id) ON DELETE CASCADE,
    position         INTEGER NOT NULL,
    model_public_id  TEXT NOT NULL,
    CONSTRAINT user_model_combo_item_position_check CHECK (position >= 0),
    CONSTRAINT user_model_combo_item_pos_uniq UNIQUE (combo_id, position)
);

CREATE INDEX IF NOT EXISTS idx_user_model_combo_item_combo
    ON user_model_combo_item (combo_id, position);

INSERT INTO app_setting (key, value, updated_at)
VALUES ('smart_llm_router_enabled', 'false', now())
ON CONFLICT (key) DO NOTHING;
