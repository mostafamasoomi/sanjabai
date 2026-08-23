-- Give a user a way to switch one of their skills on for their own chats.
--
-- Why this table did not exist before. Measured 2026-08-23, ninth session,
-- reproducing the eighth session's finding rather than trusting it. A grep
-- for the word "skill" across all seven chat-path modules (chat.py,
-- chat_smart.py, chat_stream.py, chat_billing.py, chat_web.py,
-- chat_search.py, chat_models.py) and services/context_injection.py returned
-- zero files. POST /skills/{template_id}/use substitutes the variables into
-- prompt_template and returns the rendered string to the frontend -- so a
-- skill was a template library, never an injectable capability, and no skill
-- a user created could reach the model at all.
--
-- The owner's instruction, 2026-08-23. "Even if the user added a memory or a
-- skill from the panel, it must be applied to the request." Memory already
-- was (services/context_injection.py, called from six chat call sites); a
-- skill was not. This table is the missing half.
--
-- Shape. One row per (user, template) the user switched on. The row is the
-- user's own explicit act, which is what makes injecting it consistent with
-- the same instruction's other half -- we must not induce tokens the user
-- did not ask for. A user with no rows here gets a byte-for-byte unchanged
-- request, so this change costs a non-adopting user exactly zero tokens.
--
-- enabled is kept as a column rather than deleting the row on switch-off so
-- that position (the user's ordering) survives a toggle round-trip.
--
-- Column types mirror models.py UserSkillActivation exactly, because
-- tests/test_schema_drift_all_orm.py compares every ORM table against this
-- migration corpus and a mismatch here is the same bug class that produced
-- migrations 0033, 0037, 0038 and 0039.
--
-- Idempotent by IF NOT EXISTS on both the table and its unique index, in
-- line with every migration since 0023. No backfill -- skill_templates has
-- zero rows in production (verified 2026-08-23), so there is nothing for an
-- existing user to have activated.

CREATE TABLE IF NOT EXISTS user_skill_activations (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    template_id BIGINT NOT NULL REFERENCES skill_templates(id),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_user_skill_activations_user_id ON user_skill_activations (user_id);
CREATE INDEX IF NOT EXISTS ix_user_skill_activations_template_id ON user_skill_activations (template_id);

-- One activation row per user per template. Without this a double-click on
-- the panel toggle writes two rows and the skill gets injected twice, which
-- would double the tokens the user pays for.
CREATE UNIQUE INDEX IF NOT EXISTS ux_user_skill_activations_user_template
    ON user_skill_activations (user_id, template_id);
