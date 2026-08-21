-- 0028_public_model_ids.sql
--
-- Public model ids must not leak the upstream route (ag/, kr/, cc/, cx/,
-- gemini-api/, bynara/, nvidia/, ...) and must not say "free" -- every model is
-- sold, including supply we source for free. `public_id` becomes the ONLY id
-- served by /v1/models and /api/catalog/*.
--
-- model_catalog.id and provider_model_id are deliberately UNCHANGED. `id` is a
-- TEXT primary key with foreign-key dependents (credit_packages.model_id,
-- logical_model_candidate.catalog_id, logical_model.pinned_candidate_id), and
-- it stays resolvable in chat.py indefinitely, so every existing consumer with
-- a hardcoded id keeps working -- same route, same price. Nothing expires.
--
-- public_id is derived from the LAST path segment of the id, so no route
-- prefix can survive by construction. A row with public_id IS NULL is simply
-- not publicly listable, and that is the safe default: the health checker
-- promotes rows to `available` on its own, and without this rule an
-- auto-promoted row would leak its raw prefixed id straight into the catalog.
-- Only rows that were servable when this was written (available or degraded)
-- are named here; everything else -- including the removed freellmapi supply --
-- stays NULL until an admin names it deliberately.
--
-- Where two rows claim the same public id (one model reachable over two
-- routes) exactly one wins, by health first and context window second. Losers
-- keep their own id, price and route and are only absent from public listings.
-- Verified before writing this: every colliding pair prices identically, so
-- the choice moves no money.

ALTER TABLE model_catalog ADD COLUMN IF NOT EXISTS public_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_model_catalog_public_id
    ON model_catalog (public_id) WHERE public_id IS NOT NULL;

-- public_id assignment (idempotent: re-running writes the same values)
UPDATE model_catalog SET public_id = 'sanjab/agnes-2.0-flash' WHERE id = 'agnes-2.0-flash';
UPDATE model_catalog SET public_id = 'sanjab/claude-fable-5' WHERE id = 'cc/claude-fable-5';
UPDATE model_catalog SET public_id = 'sanjab/claude-haiku-4-5-20251001' WHERE id = 'cc/claude-haiku-4-5-20251001';
UPDATE model_catalog SET public_id = 'sanjab/claude-haiku-4.5' WHERE id = 'kr/claude-haiku-4.5';
UPDATE model_catalog SET public_id = 'sanjab/claude-opus-4-8' WHERE id = 'cc/claude-opus-4-8';
UPDATE model_catalog SET public_id = 'sanjab/claude-opus-5' WHERE id = 'cc/claude-opus-5';
UPDATE model_catalog SET public_id = 'sanjab/claude-sonnet-4' WHERE id = 'kr/claude-sonnet-4';
UPDATE model_catalog SET public_id = 'sanjab/claude-sonnet-4.5' WHERE id = 'kr/claude-sonnet-4.5';
UPDATE model_catalog SET public_id = 'sanjab/claude-sonnet-5' WHERE id = 'cc/claude-sonnet-5';
UPDATE model_catalog SET public_id = 'sanjab/deepseek-3.2' WHERE id = 'kr/deepseek-3.2';
UPDATE model_catalog SET public_id = 'sanjab/gemini-2.5-flash-lite' WHERE id = 'gemini-api/models/gemini-2.5-flash-lite';
UPDATE model_catalog SET public_id = 'sanjab/gemini-3-flash' WHERE id = 'ag/gemini-3-flash';
UPDATE model_catalog SET public_id = 'sanjab/gemini-3-flash-preview' WHERE id = 'gemini-api/models/gemini-3-flash-preview';
UPDATE model_catalog SET public_id = 'sanjab/gemini-3.1-flash-lite' WHERE id = 'gemini-api/models/gemini-3.1-flash-lite';
UPDATE model_catalog SET public_id = 'sanjab/gemini-3.1-flash-lite-preview' WHERE id = 'gemini-api/models/gemini-3.1-flash-lite-preview';
UPDATE model_catalog SET public_id = 'sanjab/gemini-3.1-pro-low' WHERE id = 'ag/gemini-3.1-pro-low';
UPDATE model_catalog SET public_id = 'sanjab/gemini-3.5-flash' WHERE id = 'gemini-api/models/gemini-3.5-flash';
UPDATE model_catalog SET public_id = 'sanjab/gemini-3.5-flash-lite' WHERE id = 'gemini-api/models/gemini-3.5-flash-lite';
UPDATE model_catalog SET public_id = 'sanjab/gemini-3.6-flash-medium' WHERE id = 'agy/gemini-3.6-flash-medium';
UPDATE model_catalog SET public_id = 'sanjab/gemini-flash-lite-latest' WHERE id = 'gemini-api/models/gemini-flash-lite-latest';
UPDATE model_catalog SET public_id = 'sanjab/gemini-robotics-er-1.6-preview' WHERE id = 'gemini-api/models/gemini-robotics-er-1.6-preview';
UPDATE model_catalog SET public_id = 'sanjab/gemini-robotics-er-2-preview' WHERE id = 'gemini-api/models/gemini-robotics-er-2-preview';
UPDATE model_catalog SET public_id = 'sanjab/gemma-4-26b-a4b-it' WHERE id = 'gemini-api/models/gemma-4-26b-a4b-it';
UPDATE model_catalog SET public_id = 'sanjab/gemma-4-31b-it' WHERE id = 'gemini-api/models/gemma-4-31b-it';
UPDATE model_catalog SET public_id = 'sanjab/glm-5' WHERE id = 'kr/glm-5';
UPDATE model_catalog SET public_id = 'sanjab/gpt-5.4-mini' WHERE id = 'cx/gpt-5.4-mini';
UPDATE model_catalog SET public_id = 'sanjab/gpt-5.5' WHERE id = 'cx/gpt-5.5';
UPDATE model_catalog SET public_id = 'sanjab/gpt-5.6-luna' WHERE id = 'cx/gpt-5.6-luna';
UPDATE model_catalog SET public_id = 'sanjab/gpt-5.6-terra' WHERE id = 'cx/gpt-5.6-terra';
UPDATE model_catalog SET public_id = 'sanjab/laguna-s-2.1' WHERE id = 'laguna-s-2.1';
UPDATE model_catalog SET public_id = 'sanjab/mimo-v2.5' WHERE id = 'bynara/mimo-v2.5-free';
UPDATE model_catalog SET public_id = 'sanjab/minimax-m2.1' WHERE id = 'kr/minimax-m2.1';
UPDATE model_catalog SET public_id = 'sanjab/minimax-m2.5' WHERE id = 'kr/minimax-m2.5';
UPDATE model_catalog SET public_id = 'sanjab/minimax-m3' WHERE id = 'nvidia/minimaxai/minimax-m3';
UPDATE model_catalog SET public_id = 'sanjab/mistral-large' WHERE id = 'bynara/mistral-large';
UPDATE model_catalog SET public_id = 'sanjab/mistral-medium-3-5' WHERE id = 'bynaraa2/mistral-medium-3-5';
UPDATE model_catalog SET public_id = 'sanjab/qwen-3.8-max' WHERE id = 'bynara/qwen-3.8-max-free';
UPDATE model_catalog SET public_id = 'sanjab/qwen3-coder-next' WHERE id = 'kr/qwen3-coder-next';
UPDATE model_catalog SET public_id = 'sanjab/stepfun-3.7-flash' WHERE id = 'bynara/stepfun-3.7-flash';
UPDATE model_catalog SET public_id = 'sanjab/tencent-hy3' WHERE id = 'tencent-hy3-free';

-- display names that leaked a route or claimed "free"
UPDATE model_catalog SET display_name = 'Claude Haiku 4.5' WHERE id = 'kr/claude-haiku-4.5';  -- was: Claude Haiku 4.5 (kr)
UPDATE model_catalog SET display_name = 'MiniMax M3' WHERE id = 'nvidia/minimaxai/minimax-m3';  -- was: MiniMax M3 (NVIDIA NIM)
