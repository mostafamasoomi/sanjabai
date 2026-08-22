-- 0031_model_modalities.sql
--
-- Every row in model_catalog carries the column default modalities value
-- {"input": ["text"], "output": ["text"]} because model_discovery.py's
-- sync_provider() never set it -- see model_modalities.py for the full
-- derivation logic and its evidence. That default is false for the image,
-- video and vision (image-input) models already in the catalog, and
-- `modalities` is served verbatim by content.py's public API, so this
-- backfill is what actually fixes what users see.
--
-- Two guards, both required for safety on a table that already has admin
-- edits sitting in it --
--   1. WHERE modalities = the plain text/text default, so a value an admin
--      (or a later discovery sweep) has already corrected is never touched.
--   2. WHERE provenance <> 'admin-approved', matching the same guard
--      model_discovery.py's ON CONFLICT clause uses, so a curated row can
--      never be clobbered by this file even if its modalities happened to
--      still read as the default.
-- Verified against the live catalog before writing this file -- every id
-- listed below currently has provenance = 'provider' and modalities equal
-- to the default, so both guards are a no-op today and only matter as a
-- safety net for whenever this file actually runs.
--
-- The id groups below and the exact values they get were computed by
-- calling model_modalities.derive_modalities(id, raw) against the raw
-- upstream entry actually captured for that id -- see
-- backend/tests/test_model_modalities.py, which parses these same ids back
-- out of this file and asserts the Python function agrees with every one.
--
-- No DO $$ ... $$ block -- migrate.py's split_sql() splits on every
-- top-level semicolon and does not understand dollar-quoting.
-- No bare colon-followed-by-word anywhere below (comments included) --
-- SQLAlchemy's text() would read it as a bind parameter and refuse the
-- statement; see tests/test_migration_bind_params.py.

-- Pure image-generation models (input text only, output image only) -- the
-- omniroute payload's own explicit `input_modalities`/`output_modalities`
-- arrays for the openrouter/antigravity routes, and 9router capability
-- flags (imageOutput true, vision false) for the flux.2 ids reached only
-- via the name-based fallback because 9router reports no flags at all for
-- those three.
UPDATE model_catalog SET modalities = '{"input": ["text"], "output": ["image"]}'::jsonb
WHERE id IN (
    'antigravity/gemini-3.1-flash-image',
    'openrouter/black-forest-labs/flux.2-flex',
    'openrouter/black-forest-labs/flux.2-max',
    'openrouter/black-forest-labs/flux.2-pro',
    'openrouter/google/gemini-3.1-flash-image-preview',
    'openrouter/google/gemini-3-pro-image-preview',
    'openrouter/openai/gpt-5.4-image-2',
    'openrouter/openai/gpt-5-image-mini',
    'omni/openrouter/black-forest-labs/flux.2-flex',
    'omni/openrouter/black-forest-labs/flux.2-max',
    'omni/openrouter/black-forest-labs/flux.2-pro',
    'gemini-api/models/nano-banana-pro-preview'
) AND modalities = '{"input": ["text"], "output": ["text"]}'::jsonb
  AND provenance <> 'admin-approved';

-- The `agy` route for this same model reports vision input but no image
-- output in omniroute's own arrays -- a genuine, source-confirmed
-- restriction on this specific reseller route, not a media generator.
UPDATE model_catalog SET modalities = '{"input": ["text", "image"], "output": ["text"]}'::jsonb
WHERE id IN (
    'agy/gemini-3.1-flash-image'
) AND modalities = '{"input": ["text"], "output": ["text"]}'::jsonb
  AND provenance <> 'admin-approved';

-- Video-generation models -- omniroute's top-level type = video field for
-- veo/seedance, and the name-based fallback for every 9router-only row
-- (9router's capability schema has no flag that can express video output
-- at all, so these ids can never be flag-derived).
UPDATE model_catalog SET modalities = '{"input": ["text"], "output": ["video"]}'::jsonb
WHERE id IN (
    'veoaifree-web/seedance',
    'veoaifree-web/veo',
    'veo-free/seedance',
    'veo-free/veo',
    'omni/veoaifree-web/seedance',
    'omni/veoaifree-web/veo',
    'omni/veo-free/seedance',
    'omni/veo-free/veo',
    'bynara/agnes-video-v2.0',
    'gemini-api/models/veo-3.1-fast-generate-preview',
    'gemini-api/models/veo-3.1-generate-preview',
    'gemini-api/models/veo-3.1-lite-generate-preview',
    'Video'
) AND modalities = '{"input": ["text"], "output": ["text"]}'::jsonb
  AND provenance <> 'admin-approved';

-- Same model family reached through 9router instead of omniroute -- its
-- capability flags say both vision AND imageOutput true (accepts an image
-- to edit, produces an image back), which is real, independent evidence
-- from that route and is trusted as given rather than forced to agree with
-- omniroute's own (differently-scoped) claim for the same model name.
UPDATE model_catalog SET modalities = '{"input": ["text", "image"], "output": ["text", "image"]}'::jsonb
WHERE id IN (
    'omni/agy/gemini-3.1-flash-image',
    'omni/antigravity/gemini-3.1-flash-image',
    'omni/openrouter/google/gemini-3.1-flash-image-preview',
    'omni/openrouter/google/gemini-3-pro-image-preview'
) AND modalities = '{"input": ["text"], "output": ["text"]}'::jsonb
  AND provenance <> 'admin-approved';

-- 9router flags imageOutput true but vision false for these two -- image
-- out, no image in.
UPDATE model_catalog SET modalities = '{"input": ["text"], "output": ["text", "image"]}'::jsonb
WHERE id IN (
    'omni/openrouter/openai/gpt-5.4-image-2',
    'omni/openrouter/openai/gpt-5-image-mini'
) AND modalities = '{"input": ["text"], "output": ["text"]}'::jsonb
  AND provenance <> 'admin-approved';

-- Speech-to-text transcription endpoints -- audio in, text out. Both
-- upstreams' own flags are misleading here (omniroute marks
-- capabilities.vision true and even lists input_modalities as
-- ["text","image"] with no audio at all, a stale chat-completions
-- template never updated for this endpoint type), so this family is
-- id-pattern matched ahead of any flag in model_modalities.py -- see that
-- module's docstring for the full evidence. Applies to both the direct
-- omniroute route and the 9router `omni/...` mirror of the same ids.
UPDATE model_catalog SET modalities = '{"input": ["text", "audio"], "output": ["text"]}'::jsonb
WHERE id IN (
    'openrouter/microsoft/mai-transcribe-1.5',
    'openrouter/mistralai/voxtral-mini-transcribe',
    'openrouter/openai/gpt-4o-mini-transcribe',
    'openrouter/openai/gpt-4o-transcribe',
    'omni/openrouter/microsoft/mai-transcribe-1.5',
    'omni/openrouter/mistralai/voxtral-mini-transcribe',
    'omni/openrouter/openai/gpt-4o-mini-transcribe',
    'omni/openrouter/openai/gpt-4o-transcribe'
) AND modalities = '{"input": ["text"], "output": ["text"]}'::jsonb
  AND provenance <> 'admin-approved';

-- ---------------------------------------------------------------------
-- context_window / max_output_tokens backfill.
--
-- model_discovery.py's _context_window() only checked top-level upstream
-- keys and fell back to 8192 when none were present. 9router actually
-- reports the real context length nested at capabilities.contextWindow
-- (and the real output cap at capabilities.maxOutput) for almost every
-- model it lists, so 797 of this catalog's ninerouter rows -- and 23 of
-- its omniroute rows, whose payload uses a top-level key this function
-- simply never checked either -- were stuck at the 8192 fallback despite
-- the upstream actually reporting a real number. Three gemini-api rows
-- were confirmed already being served to users with the wrong value
-- before this migration was written.
--
-- _context_window()/a companion max-output helper in model_discovery.py
-- were fixed at the same time as this backfill (see that file's diff);
-- the values below were produced by running that same fixed logic against
-- the raw upstream entry captured for each id, so migration and code
-- agree by construction -- also asserted directly by
-- tests/test_model_modalities.py.
--
-- Only rows still sitting at the known-wrong sentinel (context_window =
-- 8192) are touched, and only with a value the upstream actually reports
-- for that exact id -- 7 ids that were in this same "stuck at 8192" set
-- had no matching entry left in either captured payload (the upstream
-- appears to have renamed or removed them since) and are deliberately
-- left alone rather than guessed at. A handful of ids below legitimately
-- contain a literal colon (9router route suffixes such as a trailing
-- "free" tag); each one is escaped with a backslash so SQLAlchemy's
-- text() does not mistake it for a bind parameter -- the same escape used
-- throughout this file's own UPDATE statements, just needed here inside a
-- couple of dozen literal id strings instead of prose.
UPDATE model_catalog AS mc
SET context_window = v.ctx, max_output_tokens = v.max_out
FROM (VALUES
    ('ag/claude-opus-4-6-thinking', 200000, 64000), ('ag/claude-sonnet-4-6', 1000000, 128000), ('ag/gemini-3.5-flash-extra-low', 1048576, 65536), ('ag/gemini-3.5-flash-high', 1048576, 65536),
    ('ag/gemini-3.5-flash-low', 1048576, 65536), ('ag/gemini-3.6-flash-high', 1048576, 65536), ('ag/gemini-3.6-flash-low', 1048576, 65536), ('ag/gemini-3.6-flash-medium', 1048576, 65536),
    ('ag/gemini-3-flash-agent', 1048576, 65536), ('ag/gemini-pro-agent', 1048576, 64000), ('ag/gpt-oss-120b-medium', 128000, 64000), ('bynaraa2/agnes-2.0-flash', 200000, 64000),
    ('bynaraa2/agnes-2.5-flash', 200000, 64000), ('bynaraa2/kimi-k3-free', 1048576, 131072), ('bynaraa2/laguna-s-2.1', 1000000, 32000), ('bynaraa2/ling-3.0-flash-free', 128000, 64000),
    ('bynaraa2/mimo-v2.5-free', 1048576, 131072), ('bynaraa2/mistral-large', 256000, 64000), ('bynaraa2/muse-spark-1.2-contributor-free', 200000, 64000), ('bynaraa2/nemotron-3-ultra', 128000, 64000),
    ('bynaraa2/qwen-3.8-max-free', 1000000, 65536), ('bynaraa2/stepfun-3.7-flash', 200000, 64000), ('bynaraa2/tencent-hy3-free', 200000, 64000), ('bynara/agnes-2.0-flash', 200000, 64000),
    ('bynara/agnes-2.5-flash', 200000, 64000), ('bynara/agnes-video-v2.0', 200000, 64000), ('bynara/claude-fable-5', 1000000, 128000), ('bynara/claude-opus-4.7', 1000000, 128000),
    ('bynara/claude-opus-4.8', 1000000, 128000), ('bynara/claude-opus-5', 1000000, 128000), ('bynara/claude-sonnet-5', 1000000, 128000), ('bynara/deepseek-v4-flash', 1000000, 384000),
    ('bynara/deepseek-v4-flash-alibaba', 1000000, 384000), ('bynara/deepseek-v4-flash-promo', 1000000, 384000), ('bynara/deepseek-v4-pro', 1000000, 384000), ('bynara/deepseek-v4-pro-alibaba', 1000000, 384000),
    ('bynara/glm-5.2', 200000, 128000), ('bynara/glm-5.2-alibaba', 200000, 128000), ('bynara/gpt-5.4', 400000, 128000), ('bynara/gpt-5.5', 400000, 128000),
    ('bynara/gpt-5.6-luna', 400000, 128000), ('bynara/gpt-5.6-sol', 400000, 128000), ('bynara/gpt-5.6-terra', 400000, 128000), ('bynara/happyhorse-1.1', 200000, 64000),
    ('bynara/kimi-k2.7-code', 262144, 65536), ('bynara/kimi-k2.7-code-alibaba', 262144, 65536), ('bynara/kimi-k2.7-code-free', 262144, 65536), ('bynara/kimi-k3', 1048576, 131072),
    ('bynara/kimi-k3-free', 1048576, 131072), ('bynara/laguna-s-2.1', 1000000, 32000), ('bynara/ling-3.0-flash-free', 128000, 64000), ('bynara/mimo-v2.5', 1048576, 131072),
    ('bynara/mimo-v2.5-pro', 1048576, 131072), ('bynara/mimo-v2.5-pro-ultraspeed', 1048576, 131072), ('bynara/minimax-m3', 1048576, 512000), ('bynara/mistral-medium-3-5', 128000, 64000),
    ('bynara/muse-spark-1.1', 200000, 64000), ('bynara/muse-spark-1.2-contributor-free', 200000, 64000), ('bynara/nemotron-3-ultra', 128000, 64000), ('bynara/qwen3.7-flash-alibaba', 1000000, 65536),
    ('bynara/qwen3.7-max', 1000000, 65536), ('bynara/qwen3.7-max-alibaba', 1000000, 65536), ('bynara/qwen3.7-plus', 1000000, 65536), ('bynara/qwen3.7-plus-alibaba', 1000000, 65536),
    ('bynara/qwen-3.8-max-free', 1000000, 65536), ('bynara/tencent-hy3-free', 200000, 64000), ('cc/claude-opus-4-8', 1000000, 128000), ('cc/claude-opus-5', 1000000, 128000),
    ('cx/gpt-5.3-codex-spark', 400000, 128000), ('cx/gpt-5.3-codex-spark-review', 400000, 128000), ('cx/gpt-5.4', 400000, 128000), ('cx/gpt-5.4-mini', 400000, 128000),
    ('cx/gpt-5.4-mini-review', 400000, 128000), ('cx/gpt-5.4-review', 400000, 128000), ('cx/gpt-5.5', 400000, 128000), ('cx/gpt-5.5-review', 400000, 128000),
    ('cx/gpt-5.6-luna', 272000, 128000), ('cx/gpt-5.6-luna-review', 272000, 128000), ('cx/gpt-5.6-sol', 372000, 128000), ('cx/gpt-5.6-sol-review', 372000, 128000),
    ('cx/gpt-5.6-terra', 272000, 128000), ('cx/gpt-5.6-terra-review', 272000, 128000), ('freellmapi/agnes-1.5-flash', 200000, 64000), ('freellmapi/agnes-2.0-flash', 200000, 64000),
    ('freellmapi/allam-2-7b', 200000, 64000), ('freellmapi/auto', 200000, 64000), ('freellmapi/aya-expanse-32b', 200000, 64000), ('freellmapi/aya-vision-32b', 200000, 64000),
    ('freellmapi/bazaarlink-auto', 200000, 64000), ('freellmapi/big-pickle', 200000, 64000), ('freellmapi/codestral', 256000, 64000), ('freellmapi/command-a', 128000, 64000),
    ('freellmapi/command-a-2', 128000, 64000), ('freellmapi/command-a-reasoning', 128000, 64000), ('freellmapi/command-a-translate', 128000, 64000), ('freellmapi/command-a-vision', 128000, 64000),
    ('freellmapi/command-r', 128000, 64000), ('freellmapi/command-r-2', 128000, 64000), ('freellmapi/command-r7b', 128000, 64000), ('freellmapi/compound', 200000, 64000),
    ('freellmapi/compound-mini', 200000, 64000), ('freellmapi/deepseek-r1', 128000, 64000), ('freellmapi/deepseek-r1-distill-qwen-32b', 262144, 64000), ('freellmapi/deepseek-v3.2', 128000, 64000),
    ('freellmapi/deepseek-v4-flash', 1000000, 384000), ('freellmapi/deepseek-v4-pro', 1000000, 384000), ('freellmapi/devstral', 200000, 64000), ('freellmapi/devstral-medium', 200000, 64000),
    ('freellmapi/dolphin-mistral-24b-venice', 128000, 64000), ('freellmapi/free-router', 200000, 64000), ('freellmapi/fusion', 200000, 64000), ('freellmapi/gemini-2.5-flash', 1048576, 65536),
    ('freellmapi/gemini-2.5-flash-lite', 1048576, 65536), ('freellmapi/gemini-3.1-flash-lite', 1048576, 65536), ('freellmapi/gemini-3.5-flash', 1048576, 65536), ('freellmapi/gemini-3.5-flash-lite', 1048576, 65536),
    ('freellmapi/gemini-3.6-flash', 1048576, 65536), ('freellmapi/gemini-3-flash-preview', 1048576, 65536), ('freellmapi/gemini-robotics-er-1.6-preview', 1048576, 64000), ('freellmapi/gemma-4-26b-a4b', 128000, 64000),
    ('freellmapi/gemma-4-26b-a4b-it', 128000, 64000), ('freellmapi/gemma-4-26b-it', 128000, 64000), ('freellmapi/gemma-4-31b', 128000, 64000), ('freellmapi/gemma-4-31b-it', 128000, 64000),
    ('freellmapi/gemma-sea-lion-v4-27b', 128000, 64000), ('freellmapi/glm-4.5', 200000, 64000), ('freellmapi/glm-4.5-flash', 200000, 64000), ('freellmapi/glm-4.6v-flash', 200000, 64000),
    ('freellmapi/glm-4.7', 200000, 128000), ('freellmapi/glm-4.7-flash', 200000, 128000), ('freellmapi/glm-5.2', 200000, 128000), ('freellmapi/gpt-4.1', 1000000, 32768),
    ('freellmapi/gpt-oss-120b', 128000, 64000), ('freellmapi/gpt-oss-20b', 128000, 64000), ('freellmapi/gpt-oss-safeguard-20b', 128000, 64000), ('freellmapi/granite-4.0-h-micro', 200000, 64000),
    ('freellmapi/hermes-3-405b', 200000, 64000), ('freellmapi/kilo-auto', 200000, 64000), ('freellmapi/kimi-k2.6', 262144, 262144), ('freellmapi/kimi-k2.7-code', 262144, 65536),
    ('freellmapi/laguna-s-2.1', 1000000, 32000), ('freellmapi/liquid-lfm-2.5-1.2b', 200000, 64000), ('freellmapi/liquid-lfm-2.5-1.2b-thinking', 200000, 64000), ('freellmapi/llama-3.1-70b', 128000, 64000),
    ('freellmapi/llama-3.1-8b', 128000, 64000), ('freellmapi/llama-3.1-8b-instant', 128000, 64000), ('freellmapi/llama-3.1-8b-instruct-fast', 128000, 64000), ('freellmapi/llama-3.2-11b-vision', 128000, 64000),
    ('freellmapi/llama-3.2-1b-instruct', 128000, 64000), ('freellmapi/llama-3.2-3b', 128000, 64000), ('freellmapi/llama-3.2-3b-instruct', 128000, 64000), ('freellmapi/llama-3.2-90b-vision', 128000, 64000),
    ('freellmapi/llama-3.3-70b', 128000, 64000), ('freellmapi/llama-3.3-70b-fp8-fast', 128000, 64000), ('freellmapi/llama-3.3-70b-instruct', 128000, 64000), ('freellmapi/llama-4-maverick', 1000000, 64000),
    ('freellmapi/llama-4-scout', 1000000, 64000), ('freellmapi/llama-guard-3-8b', 128000, 64000), ('freellmapi/llama-prompt-guard-2-22m', 128000, 64000), ('freellmapi/llama-prompt-guard-2-86m', 128000, 64000),
    ('freellmapi/magistral-medium', 200000, 64000), ('freellmapi/magistral-small', 200000, 64000), ('freellmapi/mimo-v2.5', 1048576, 131072), ('freellmapi/minimax-m2.7', 204800, 131072),
    ('freellmapi/minimax-m3', 1048576, 512000), ('freellmapi/ministral-14b', 200000, 64000), ('freellmapi/ministral-3-8b', 200000, 64000), ('freellmapi/mistral-7b-instruct-v0.3', 128000, 64000),
    ('freellmapi/mistral-code', 128000, 64000), ('freellmapi/mistral-code-agent', 128000, 64000), ('freellmapi/mistral-large-3', 256000, 64000), ('freellmapi/mistral-large-3-675b', 256000, 64000),
    ('freellmapi/mistral-medium-3.5', 128000, 64000), ('freellmapi/mistral-nemo', 128000, 64000), ('freellmapi/mistral-small-3.1-24b', 128000, 64000), ('freellmapi/mistral-small-3.2-24b', 128000, 64000),
    ('freellmapi/mistral-small-4', 128000, 64000), ('freellmapi/mistral-vibe-cli-fast', 128000, 64000), ('freellmapi/moondream-3.1-9b-a2b', 200000, 64000), ('freellmapi/nemotron-3-120b', 128000, 64000),
    ('freellmapi/nemotron-3.5-content-safety', 128000, 64000), ('freellmapi/nemotron-3-nano-30b', 128000, 64000), ('freellmapi/nemotron-3-nano-30b-a3b', 128000, 64000), ('freellmapi/nemotron-3-nano-30b-reasoning', 128000, 64000),
    ('freellmapi/nemotron-3-nano-omni-reasoning', 128000, 64000), ('freellmapi/nemotron-3-super', 128000, 64000), ('freellmapi/nemotron-3-super-120b', 128000, 64000), ('freellmapi/nemotron-3-ultra', 128000, 64000),
    ('freellmapi/nemotron-3-ultra-550b', 128000, 64000), ('freellmapi/nemotron-nano-12b-vl', 128000, 64000), ('freellmapi/nemotron-nano-9b-v2', 128000, 64000), ('freellmapi/nemotron-super-49b-v1.5', 128000, 64000),
    ('freellmapi/north-mini-code', 200000, 64000), ('freellmapi/poolside-laguna-m.1', 200000, 32000), ('freellmapi/poolside-laguna-s-2.1', 1000000, 32000), ('freellmapi/poolside-laguna-xs.2', 200000, 32000),
    ('freellmapi/poolside-laguna-xs-2.1', 200000, 32000), ('freellmapi/qwen2.5-coder-32b', 1000000, 64000), ('freellmapi/qwen2.5-vl-72b', 262144, 64000), ('freellmapi/qwen3-14b', 262144, 64000),
    ('freellmapi/qwen3-30b-a3b-fp8', 262144, 64000), ('freellmapi/qwen3-32b', 262144, 64000), ('freellmapi/qwen3.5-397b', 1000000, 65536), ('freellmapi/qwen3.6-27b', 1000000, 65536),
    ('freellmapi/qwen3-8b', 262144, 64000), ('freellmapi/qwen3-coder-30b', 1000000, 64000), ('freellmapi/qwen3-coder-480b', 1000000, 64000), ('freellmapi/qwen3-coder-next', 1000000, 64000),
    ('freellmapi/qwen3guard-gen-0.6b', 262144, 64000), ('freellmapi/qwen3guard-gen-8b', 262144, 64000), ('freellmapi/qwen3-next-80b', 262144, 64000), ('freellmapi/qwen3-vl-235b', 262144, 64000),
    ('freellmapi/qwq-32b', 131072, 64000), ('freellmapi/reka-edge', 200000, 64000), ('freellmapi/reka-flash', 200000, 64000), ('freellmapi-s2/agnes-2.0-flash', 200000, 64000),
    ('freellmapi-s2/allam-2-7b', 200000, 64000), ('freellmapi-s2/auto', 200000, 64000), ('freellmapi-s2/aya-expanse-32b', 200000, 64000), ('freellmapi-s2/aya-vision-32b', 200000, 64000),
    ('freellmapi-s2/bazaarlink-auto', 200000, 64000), ('freellmapi-s2/big-pickle', 200000, 64000), ('freellmapi-s2/codestral', 256000, 64000), ('freellmapi-s2/command-a', 128000, 64000),
    ('freellmapi-s2/command-a-2', 128000, 64000), ('freellmapi-s2/command-a-reasoning', 128000, 64000), ('freellmapi-s2/command-a-translate', 128000, 64000), ('freellmapi-s2/command-a-vision', 128000, 64000),
    ('freellmapi-s2/command-r', 128000, 64000), ('freellmapi-s2/command-r-2', 128000, 64000), ('freellmapi-s2/command-r7b', 128000, 64000), ('freellmapi-s2/compound', 200000, 64000),
    ('freellmapi-s2/compound-mini', 200000, 64000), ('freellmapi-s2/cydonia-24b-v4.3', 200000, 64000), ('freellmapi-s2/deepseek-r1', 128000, 64000), ('freellmapi-s2/deepseek-r1-distill-qwen-32b', 262144, 64000),
    ('freellmapi-s2/deepseek-v3.2', 128000, 64000), ('freellmapi-s2/deepseek-v4-flash', 1000000, 384000), ('freellmapi-s2/devstral', 200000, 64000), ('freellmapi-s2/devstral-medium', 200000, 64000),
    ('freellmapi-s2/free-router', 200000, 64000), ('freellmapi-s2/fusion', 200000, 64000), ('freellmapi-s2/gemini-2.5-flash', 1048576, 65536), ('freellmapi-s2/gemini-2.5-flash-lite', 1048576, 65536),
    ('freellmapi-s2/gemini-3.1-flash-lite', 1048576, 65536), ('freellmapi-s2/gemini-3.5-flash', 1048576, 65536), ('freellmapi-s2/gemini-3-flash-preview', 1048576, 65536), ('freellmapi-s2/gemma-4-26b-a4b', 128000, 64000),
    ('freellmapi-s2/gemma-4-26b-a4b-it', 128000, 64000), ('freellmapi-s2/gemma-4-26b-it', 128000, 64000), ('freellmapi-s2/gemma-4-31b', 128000, 64000), ('freellmapi-s2/gemma-4-31b-it', 128000, 64000),
    ('freellmapi-s2/gemma-sea-lion-v4-27b', 128000, 64000), ('freellmapi-s2/glm-4.5-flash', 200000, 64000), ('freellmapi-s2/glm-4.6v-flash', 200000, 64000), ('freellmapi-s2/glm-4.7', 200000, 128000),
    ('freellmapi-s2/glm-4.7-flash', 200000, 128000), ('freellmapi-s2/glm-5.2', 200000, 128000), ('freellmapi-s2/gpt-oss-120b', 128000, 64000), ('freellmapi-s2/gpt-oss-20b', 128000, 64000),
    ('freellmapi-s2/gpt-oss-safeguard-20b', 128000, 64000), ('freellmapi-s2/granite-4.0-h-micro', 200000, 64000), ('freellmapi-s2/kilo-auto', 200000, 64000), ('freellmapi-s2/kimi-k2.6', 262144, 262144),
    ('freellmapi-s2/kimi-k2.7-code', 262144, 65536), ('freellmapi-s2/llama-3.1-70b', 128000, 64000), ('freellmapi-s2/llama-3.1-8b', 128000, 64000), ('freellmapi-s2/llama-3.1-8b-instant', 128000, 64000),
    ('freellmapi-s2/llama-3.1-8b-instruct-fast', 128000, 64000), ('freellmapi-s2/llama-3.2-11b-vision', 128000, 64000), ('freellmapi-s2/llama-3.2-1b-instruct', 128000, 64000), ('freellmapi-s2/llama-3.2-3b', 128000, 64000),
    ('freellmapi-s2/llama-3.2-3b-instruct', 128000, 64000), ('freellmapi-s2/llama-3.2-90b-vision', 128000, 64000), ('freellmapi-s2/llama-3.3-70b', 128000, 64000), ('freellmapi-s2/llama-3.3-70b-fp8-fast', 128000, 64000),
    ('freellmapi-s2/llama-3.3-70b-instruct', 128000, 64000), ('freellmapi-s2/llama-4-maverick', 1000000, 64000), ('freellmapi-s2/llama-4-scout', 1000000, 64000), ('freellmapi-s2/llama-guard-3-8b', 128000, 64000),
    ('freellmapi-s2/magistral-medium', 200000, 64000), ('freellmapi-s2/magistral-small', 200000, 64000), ('freellmapi-s2/mimo-v2.5', 1048576, 131072), ('freellmapi-s2/minimax-m3', 1048576, 512000),
    ('freellmapi-s2/ministral-14b', 200000, 64000), ('freellmapi-s2/ministral-3-8b', 200000, 64000), ('freellmapi-s2/mistral-7b-instruct-v0.3', 128000, 64000), ('freellmapi-s2/mistral-code', 128000, 64000),
    ('freellmapi-s2/mistral-code-agent', 128000, 64000), ('freellmapi-s2/mistral-large-3', 256000, 64000), ('freellmapi-s2/mistral-medium-3.5', 128000, 64000), ('freellmapi-s2/mistral-nemo', 128000, 64000),
    ('freellmapi-s2/mistral-small-3.1-24b', 128000, 64000), ('freellmapi-s2/mistral-small-3.2-24b', 128000, 64000), ('freellmapi-s2/mistral-small-4', 128000, 64000), ('freellmapi-s2/mistral-vibe-cli-fast', 128000, 64000),
    ('freellmapi-s2/moondream-3.1-9b-a2b', 200000, 64000), ('freellmapi-s2/nemotron-3-120b', 128000, 64000), ('freellmapi-s2/nemotron-3.5-content-safety', 128000, 64000), ('freellmapi-s2/nemotron-3-nano-30b', 128000, 64000),
    ('freellmapi-s2/nemotron-3-nano-30b-a3b', 128000, 64000), ('freellmapi-s2/nemotron-3-nano-30b-reasoning', 128000, 64000), ('freellmapi-s2/nemotron-3-nano-omni-reasoning', 128000, 64000), ('freellmapi-s2/nemotron-3-super', 128000, 64000),
    ('freellmapi-s2/nemotron-3-super-120b', 128000, 64000), ('freellmapi-s2/nemotron-3-ultra', 128000, 64000), ('freellmapi-s2/nemotron-3-ultra-550b', 128000, 64000), ('freellmapi-s2/nemotron-nano-12b-vl', 128000, 64000),
    ('freellmapi-s2/nemotron-nano-9b-v2', 128000, 64000), ('freellmapi-s2/nemotron-super-49b-v1.5', 128000, 64000), ('freellmapi-s2/north-mini-code', 200000, 64000), ('freellmapi-s2/poolside-laguna-xs-2.1', 200000, 32000),
    ('freellmapi-s2/qwen2.5-coder-32b', 1000000, 64000), ('freellmapi-s2/qwen2.5-vl-72b', 262144, 64000), ('freellmapi-s2/qwen3-14b', 262144, 64000), ('freellmapi-s2/qwen3-30b-a3b-fp8', 262144, 64000),
    ('freellmapi-s2/qwen3-32b', 262144, 64000), ('freellmapi-s2/qwen3.5-397b', 1000000, 65536), ('freellmapi-s2/qwen3.6-27b', 1000000, 65536), ('freellmapi-s2/qwen3-8b', 262144, 64000),
    ('freellmapi-s2/qwen3-coder-30b', 1000000, 64000), ('freellmapi-s2/qwen3-coder-480b', 1000000, 64000), ('freellmapi-s2/qwen3-coder-next', 1000000, 64000), ('freellmapi-s2/qwen3guard-gen-0.6b', 262144, 64000),
    ('freellmapi-s2/qwen3guard-gen-8b', 262144, 64000), ('freellmapi-s2/qwen3-vl-235b', 262144, 64000), ('freellmapi-s2/qwq-32b', 131072, 64000), ('freellmapi-s2/reka-edge', 200000, 64000),
    ('freellmapi-s2/reka-flash', 200000, 64000), ('freellmapi-s2/step-3.7-flash', 128000, 64000), ('freellmapi-s2/stepfun-step-3.7-flash', 128000, 64000), ('freellmapi-s3/auto', 200000, 64000),
    ('freellmapi-s3/big-pickle', 200000, 64000), ('freellmapi-s3/codestral', 256000, 64000), ('freellmapi-s3/command-a', 128000, 64000), ('freellmapi-s3/command-a-reasoning', 128000, 64000),
    ('freellmapi-s3/command-r', 128000, 64000), ('freellmapi-s3/command-r-2', 128000, 64000), ('freellmapi-s3/compound', 200000, 64000), ('freellmapi-s3/compound-mini', 200000, 64000),
    ('freellmapi-s3/deepseek-r1-distill-qwen-32b', 262144, 64000), ('freellmapi-s3/deepseek-v4-flash', 1000000, 384000), ('freellmapi-s3/deepseek-v4-pro', 1000000, 384000), ('freellmapi-s3/devstral', 200000, 64000),
    ('freellmapi-s3/dolphin-mistral-24b-venice', 128000, 64000), ('freellmapi-s3/fusion', 200000, 64000), ('freellmapi-s3/gemini-2.5-flash', 1048576, 65536), ('freellmapi-s3/gemini-2.5-flash-lite', 1048576, 65536),
    ('freellmapi-s3/gemini-3.5-flash', 1048576, 65536), ('freellmapi-s3/gemma-4-26b-a4b', 128000, 64000), ('freellmapi-s3/gemma-4-26b-a4b-it', 128000, 64000), ('freellmapi-s3/gemma-4-26b-it', 128000, 64000),
    ('freellmapi-s3/gemma-4-31b', 128000, 64000), ('freellmapi-s3/gemma-4-31b-it', 128000, 64000), ('freellmapi-s3/glm-4.6v-flash', 200000, 64000), ('freellmapi-s3/glm-4.7', 200000, 128000),
    ('freellmapi-s3/glm-4.7-flash', 200000, 128000), ('freellmapi-s3/glm-5.1', 200000, 128000), ('freellmapi-s3/gpt-4.1', 1000000, 32768), ('freellmapi-s3/gpt-oss-120b', 128000, 64000),
    ('freellmapi-s3/gpt-oss-20b', 128000, 64000), ('freellmapi-s3/gpt-oss-safeguard-20b', 128000, 64000), ('freellmapi-s3/granite-4.0-h-micro', 200000, 64000), ('freellmapi-s3/hermes-3-405b', 200000, 64000),
    ('freellmapi-s3/kimi-k2.6', 262144, 262144), ('freellmapi-s3/liquid-lfm-2.5-1.2b', 200000, 64000), ('freellmapi-s3/liquid-lfm-2.5-1.2b-thinking', 200000, 64000), ('freellmapi-s3/llama-3.1-70b', 128000, 64000),
    ('freellmapi-s3/llama-3.1-8b-instant', 128000, 64000), ('freellmapi-s3/llama-3.2-3b', 128000, 64000), ('freellmapi-s3/llama-3.3-70b', 128000, 64000), ('freellmapi-s3/llama-3.3-70b-fp8-fast', 128000, 64000),
    ('freellmapi-s3/llama-4-maverick', 1000000, 64000), ('freellmapi-s3/llama-4-scout', 1000000, 64000), ('freellmapi-s3/magistral-medium', 200000, 64000), ('freellmapi-s3/mimo-v2.5', 1048576, 131072),
    ('freellmapi-s3/minimax-m2.7', 204800, 131072), ('freellmapi-s3/ministral-3-8b', 200000, 64000), ('freellmapi-s3/mistral-large-3', 256000, 64000), ('freellmapi-s3/mistral-large-3-675b', 256000, 64000),
    ('freellmapi-s3/mistral-medium-3.5', 128000, 64000), ('freellmapi-s3/mistral-small-4', 128000, 64000), ('freellmapi-s3/nemotron-3-120b', 128000, 64000), ('freellmapi-s3/nemotron-3-nano-30b', 128000, 64000),
    ('freellmapi-s3/nemotron-3-nano-30b-reasoning', 128000, 64000), ('freellmapi-s3/nemotron-3-super-120b', 128000, 64000), ('freellmapi-s3/nemotron-3-ultra-550b', 128000, 64000), ('freellmapi-s3/nemotron-nano-9b-v2', 128000, 64000),
    ('freellmapi-s3/poolside-laguna-m.1', 200000, 32000), ('freellmapi-s3/poolside-laguna-xs.2', 200000, 32000), ('freellmapi-s3/qwen3-30b-a3b-fp8', 262144, 64000), ('freellmapi-s3/qwen3-coder-480b', 1000000, 64000),
    ('freellmapi-s3/qwen3-coder-next', 1000000, 64000), ('freellmapi-s3/qwen3-next-80b', 262144, 64000), ('freellmapi-s3/stepfun-step-3.7-flash', 128000, 64000), ('freellmapi/step-3.7-flash', 128000, 64000),
    ('freellmapi/stepfun-step-3.7-flash', 128000, 64000), ('gc/gemini-2.5-flash', 1048576, 65536), ('gc/gemini-2.5-flash-lite', 1048576, 65536), ('gc/gemini-2.5-pro', 1048576, 65536),
    ('gc/gemini-3.1-flash-lite-preview', 1048576, 65536), ('gc/gemini-3.1-pro-preview', 1048576, 65535), ('gc/gemini-3-flash-preview', 1048576, 65536), ('gc/gemini-3-pro-preview', 1048576, 65535),
    ('gemini-api/models/antigravity-preview-05-2026', 200000, 64000), ('gemini-api/models/aqa', 200000, 64000), ('gemini-api/models/deep-research-max-preview-04-2026', 200000, 64000), ('gemini-api/models/deep-research-preview-04-2026', 200000, 64000),
    ('gemini-api/models/deep-research-pro-preview-12-2025', 200000, 64000), ('gemini-api/models/gemini-2.5-computer-use-preview-10-2025', 1048576, 65536), ('gemini-api/models/gemini-2.5-flash', 1048576, 65536), ('gemini-api/models/gemini-2.5-flash-lite', 1048576, 65536),
    ('gemini-api/models/gemini-3.1-flash-live-preview', 1048576, 65536), ('gemini-api/models/gemini-3.1-pro-preview', 1048576, 65535), ('gemini-api/models/gemini-3.1-pro-preview-customtools', 1048576, 65535), ('gemini-api/models/gemini-3.5-flash', 1048576, 65536),
    ('gemini-api/models/gemini-3.5-live-translate-preview', 1048576, 65536), ('gemini-api/models/gemini-3.6-flash', 1048576, 65536), ('gemini-api/models/gemini-3.7-flash', 1048576, 65536), ('gemini-api/models/gemini-flash-latest', 1048576, 64000),
    ('gemini-api/models/gemini-omni-flash-preview', 1048576, 64000), ('gemini-api/models/gemini-pro-latest', 1048576, 64000), ('gemini-api/models/gemini-robotics-er-2-streaming-preview', 1048576, 64000), ('gemini-api/models/lyria-3-clip-preview', 200000, 64000),
    ('gemini-api/models/lyria-3-pro-preview', 200000, 64000), ('gemini-api/models/lyria-realtime-exp', 200000, 64000), ('gemini-api/models/nano-banana-pro-preview', 200000, 64000), ('gemini-api/models/veo-3.1-fast-generate-preview', 200000, 64000),
    ('gemini-api/models/veo-3.1-generate-preview', 200000, 64000), ('gemini-api/models/veo-3.1-lite-generate-preview', 200000, 64000), ('kc/anthropic/claude-opus-4-20250514', 200000, 64000), ('kc/anthropic/claude-sonnet-4-20250514', 200000, 64000),
    ('kc/cohere/north-mini-code\:free', 200000, 64000), ('kc/deepseek/deepseek-chat', 128000, 64000), ('kc/deepseek/deepseek-reasoner', 128000, 64000), ('kc/google/gemini-2.5-flash', 1048576, 65536),
    ('kc/google/gemini-2.5-pro', 1048576, 65536), ('kc/google/lyria-3-clip-preview', 200000, 64000), ('kc/google/lyria-3-pro-preview', 200000, 64000), ('kc/inclusionai/ling-3.0-flash\:free', 128000, 64000),
    ('kc/kilo-auto/free', 200000, 64000), ('kc/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning\:free', 128000, 64000), ('kc/nvidia/nemotron-3-super-120b-a12b\:free', 128000, 64000), ('kc/nvidia/nemotron-3-ultra-550b-a55b\:free', 128000, 64000),
    ('kc/openai/gpt-4.1', 1000000, 32768), ('kc/openai/o3', 200000, 100000), ('kc/openrouter/free', 200000, 64000), ('kc/poolside/laguna-m.1\:free', 200000, 32000),
    ('kc/poolside/laguna-s-2.1\:free', 200000, 32000), ('kc/poolside/laguna-xs-2.1\:free', 200000, 32000), ('kimchi/deepseek-v4-flash', 1048576, 384000), ('kimchi/deepseek-v4-flash-0731', 1048576, 512000),
    ('kimchi/kimi-k2.7', 262144, 60000), ('kimchi/minimax-m3', 1048576, 524288), ('kimchi/nemotron-3-ultra-fp4', 1048576, 66000), ('mimo/mimo-v2-flash', 262144, 131072),
    ('mimo/mimo-v2-omni', 262144, 131072), ('nvidia/deepseek-ai/deepseek-v4-flash', 1000000, 65536), ('nvidia/deepseek-ai/deepseek-v4-pro', 1000000, 65536), ('nvidia/minimaxai/minimax-m2.7', 200000, 131072),
    ('nvidia/moonshotai/kimi-k2.6', 262144, 262144), ('nvidia/nemotron-3-ultra-550b-a55b', 128000, 64000), ('nvidia/parakeet-ctc-1.1b-asr', 200000, 64000), ('nvidia/z-ai/glm-5.2', 200000, 128000),
    ('ocg/glm-5.1', 200000, 128000), ('ocg/glm-5.2', 200000, 128000), ('ocg/glm-5.3', 200000, 128000), ('ocg/kimi-k2.7-code', 262144, 65536),
    ('ocg/kimi-k3', 1048576, 131072), ('ocg/mimo-v2.5', 1048576, 131072), ('ocg/mimo-v2.5-pro', 1048576, 131072), ('omni/agy/claude-opus-4-6-thinking', 200000, 64000),
    ('omni/agy/claude-opus-4-6-thinking-high', 200000, 64000), ('omni/agy/claude-opus-4-6-thinking-low', 200000, 64000), ('omni/agy/claude-opus-4-6-thinking-medium', 200000, 64000), ('omni/agy/claude-sonnet-4-6', 1000000, 128000),
    ('omni/agy/claude-sonnet-4-6-high', 200000, 64000), ('omni/agy/claude-sonnet-4-6-low', 200000, 64000), ('omni/agy/claude-sonnet-4-6-medium', 200000, 64000), ('omni/agy/gemini-2.5-flash', 1048576, 65536),
    ('omni/agy/gemini-2.5-flash-lite', 1048576, 65536), ('omni/agy/gemini-2.5-flash-thinking', 1048576, 65536), ('omni/agy/gemini-2.5-pro', 1048576, 65536), ('omni/agy/gemini-3.1-flash-image', 1048576, 64000),
    ('omni/agy/gemini-3.1-flash-lite', 1048576, 65536), ('omni/agy/gemini-3.1-pro-high', 1048576, 65535), ('omni/agy/gemini-3.1-pro-low', 1048576, 65535), ('omni/agy/gemini-3.5-flash-extra-low', 1048576, 65536),
    ('omni/agy/gemini-3.5-flash-low', 1048576, 65536), ('omni/agy/gemini-3.6-flash-high', 1048576, 65536), ('omni/agy/gemini-3.6-flash-low', 1048576, 65536), ('omni/agy/gemini-3.6-flash-medium', 1048576, 65536),
    ('omni/agy/gemini-3.6-flash-tiered', 1048576, 65536), ('omni/agy/gemini-3.7-flash-high', 1048576, 65536), ('omni/agy/gemini-3.7-flash-low', 1048576, 65536), ('omni/agy/gemini-3.7-flash-medium', 1048576, 65536),
    ('omni/agy/gemini-3.7-flash-tiered', 1048576, 65536), ('omni/agy/gemini-3-flash', 1048576, 65536), ('omni/agy/gemini-3-flash-agent', 1048576, 65536), ('omni/agy/gemini-pro-agent', 1048576, 64000),
    ('omni/agy/gpt-oss-120b-medium', 128000, 64000), ('omni/antigravity/claude-opus-4-6-thinking', 200000, 64000), ('omni/antigravity/claude-opus-4-6-thinking-high', 200000, 64000), ('omni/antigravity/claude-opus-4-6-thinking-low', 200000, 64000),
    ('omni/antigravity/claude-opus-4-6-thinking-medium', 200000, 64000), ('omni/antigravity/claude-sonnet-4-6', 1000000, 128000), ('omni/antigravity/claude-sonnet-4-6-high', 200000, 64000), ('omni/antigravity/claude-sonnet-4-6-low', 200000, 64000),
    ('omni/antigravity/claude-sonnet-4-6-medium', 200000, 64000), ('omni/antigravity/gemini-2.5-flash', 1048576, 65536), ('omni/antigravity/gemini-2.5-flash-lite', 1048576, 65536), ('omni/antigravity/gemini-2.5-flash-thinking', 1048576, 65536),
    ('omni/antigravity/gemini-3.1-flash-image', 1048576, 64000), ('omni/antigravity/gemini-3.1-flash-lite', 1048576, 65536), ('omni/antigravity/gemini-3.1-pro-low', 1048576, 65535), ('omni/antigravity/gemini-3.5-flash-extra-low', 1048576, 65536),
    ('omni/antigravity/gemini-3.5-flash-low', 1048576, 65536), ('omni/antigravity/gemini-3.6-flash-high', 1048576, 65536), ('omni/antigravity/gemini-3.6-flash-low', 1048576, 65536), ('omni/antigravity/gemini-3.6-flash-medium', 1048576, 65536),
    ('omni/antigravity/gemini-3-flash-agent', 1048576, 65536), ('omni/antigravity/gemini-pro-agent', 1048576, 64000), ('omni/aug/fable-5', 200000, 64000), ('omni/aug/gemini-3.1-pro-preview', 1048576, 65535),
    ('omni/aug/glm-5.2', 200000, 128000), ('omni/aug/gpt5', 200000, 64000), ('omni/aug/gpt5.1', 200000, 64000), ('omni/aug/gpt5.2', 200000, 64000),
    ('omni/aug/gpt5.4', 200000, 64000), ('omni/aug/gpt5.4-mini', 200000, 64000), ('omni/aug/gpt5.5', 200000, 64000), ('omni/aug/gpt5.6-luna', 200000, 64000),
    ('omni/aug/gpt5.6-sol', 200000, 64000), ('omni/aug/gpt5.6-terra', 200000, 64000), ('omni/aug/haiku4.5', 200000, 64000), ('omni/aug/kimi-k2.6', 262144, 262144),
    ('omni/aug/kimi-k2.7', 262144, 262144), ('omni/aug/opus4.5', 200000, 64000), ('omni/aug/opus4.6', 200000, 64000), ('omni/aug/opus4.6-500k', 200000, 64000),
    ('omni/aug/opus4.7', 200000, 64000), ('omni/aug/opus4.7-500k', 200000, 64000), ('omni/aug/opus4.8', 200000, 64000), ('omni/aug/prism-a', 200000, 64000),
    ('omni/aug/prism-b', 200000, 64000), ('omni/aug/sonnet4.5', 200000, 64000), ('omni/aug/sonnet4.6', 200000, 64000), ('omni/aug/sonnet4.6-500k', 200000, 64000),
    ('omni/aug/sonnet5-500k', 200000, 64000), ('omni/aug/sonnet5-high', 200000, 64000), ('omni/auto/best-chaos', 200000, 64000), ('omni/auto/best-chat', 200000, 64000),
    ('omni/auto/best-coding', 200000, 64000), ('omni/auto/best-coding-fast', 200000, 64000), ('omni/auto/best-fast', 200000, 64000), ('omni/auto/best-free', 200000, 64000),
    ('omni/auto/best-reasoning', 200000, 64000), ('omni/auto/best-vision', 200000, 64000), ('omni/auto/chaos', 200000, 64000), ('omni/auto/chat', 200000, 64000),
    ('omni/auto/cheap', 200000, 64000), ('omni/auto/claude-opus', 200000, 64000), ('omni/auto/claude-sonnet', 200000, 64000), ('omni/auto/coding', 200000, 64000),
    ('omni/auto/coding\:cheap', 200000, 64000), ('omni/auto/coding\:fast', 200000, 64000), ('omni/auto/coding\:free', 200000, 64000), ('omni/auto/coding\:pro', 200000, 64000),
    ('omni/auto/coding\:reliable', 200000, 64000), ('omni/auto/fast', 200000, 64000), ('omni/auto/gemini', 1048576, 64000), ('omni/auto/gemma', 128000, 64000),
    ('omni/auto/glm', 200000, 64000), ('omni/auto/llama', 128000, 64000), ('omni/auto/mimo', 262144, 131072), ('omni/auto/minimax', 200000, 131072),
    ('omni/auto/multimodal', 200000, 64000), ('omni/auto/offline', 200000, 64000), ('omni/auto/pro-chat', 200000, 64000), ('omni/auto/pro-coding', 200000, 64000),
    ('omni/auto/pro-fast', 200000, 64000), ('omni/auto/pro-reasoning', 200000, 64000), ('omni/auto/pro-vision', 200000, 64000), ('omni/auto/reasoning', 200000, 64000),
    ('omni/auto/reasoning\:pro', 200000, 64000), ('omni/auto/smart', 200000, 64000), ('omni/auto/vision', 200000, 64000), ('omni/auto/zai', 200000, 64000),
    ('omni/cf/@cf/deepseek-ai/deepseek-r1-distill-qwen-32b', 262144, 64000), ('omni/cf/@cf/google/gemma-4-26b-a4b-it', 128000, 64000), ('omni/cf/@cf/mistral/mistral-7b-instruct-v0.2-lora', 128000, 64000), ('omni/cf/@cf/qwen/qwq-32b', 131072, 64000),
    ('omni/cf/@cf/zai-org/glm-4.7-flash', 200000, 128000), ('omni/cloudflare-ai/@cf/deepseek-ai/deepseek-r1-distill-qwen-32b', 262144, 64000), ('omni/cloudflare-ai/@cf/google/gemma-4-26b-a4b-it', 128000, 64000), ('omni/cloudflare-ai/@cf/mistral/mistral-7b-instruct-v0.2-lora', 128000, 64000),
    ('omni/cloudflare-ai/@cf/qwen/qwq-32b', 131072, 64000), ('omni/cloudflare-ai/@cf/zai-org/glm-4.7-flash', 200000, 128000), ('omni/ddgw/claude-haiku-4-5', 200000, 64000), ('omni/ddgw/gpt-5.4-mini', 400000, 128000),
    ('omni/ddgw/gpt-5.4-nano', 400000, 128000), ('omni/ddgw/mistral-small-2603', 128000, 64000), ('omni/ddgw/tinfoil/gemma4-31b', 128000, 64000), ('omni/ddgw/tinfoil/gpt-oss-120b', 128000, 64000),
    ('omni/deepseek/deepseek-v4-flash', 1000000, 384000), ('omni/deepseek/deepseek-v4-pro', 1000000, 384000), ('omni/ds/deepseek-v4-flash', 1000000, 384000), ('omni/ds/deepseek-v4-pro', 1000000, 384000),
    ('omni/felo/felo-chat', 200000, 64000), ('omni/felo/felo-document', 200000, 64000), ('omni/felo/felo-scholar', 200000, 64000), ('omni/felo/felo-search', 200000, 64000),
    ('omni/felo/felo-social', 200000, 64000), ('omni/horde/Angelic_Eclipse-12B', 200000, 64000), ('omni/horde/Artemis-31B-v1m-Q6_K.gguf', 200000, 64000), ('omni/horde/Behemoth-128B-v3b-Q4_K_M', 200000, 64000),
    ('omni/horde/gemma-4-12b-it-Q4_K_M', 128000, 64000), ('omni/horde/gemma-4-31B-it-heretic', 128000, 64000), ('omni/horde/gemma-4-31B-it-Q4_K_M', 128000, 64000), ('omni/horde/Gemma-4-E4B-it-Ultra-Uncensored-Heretic', 128000, 64000),
    ('omni/horde/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive', 128000, 64000), ('omni/horde/Huihui-Qwen3.5-0.8B-abliterated.Q4_K_M', 1000000, 65536), ('omni/horde/Judas-Uncensored-3.2-1B.Q8', 200000, 64000), ('omni/horde/L3-8B-Stheno-v3.2', 200000, 64000),
    ('omni/horde/L3-8B-Stheno-v3.2-Q4_K_S', 200000, 64000), ('omni/horde/L3-8B-Stheno-v3.2-Q5_K_M', 200000, 64000), ('omni/horde/L3-8B-Stheno-v3.2-Q8_0', 200000, 64000), ('omni/horde/L3-Super-Nova-RP-8B', 200000, 64000),
    ('omni/horde/Llama-3.2-1B-Instruct', 128000, 64000), ('omni/horde/Llama-3.2-3B', 128000, 64000), ('omni/horde/Llama-3-Lumimaid-8B-v0.1', 128000, 64000), ('omni/horde/Magidonia-24B-v4.3', 200000, 64000),
    ('omni/horde/mini-magnum-12b-v1.1', 200000, 64000), ('omni/horde/modelo8b', 200000, 64000), ('omni/horde/Qwen_Qwen3-0.6B-IQ4_XS', 262144, 64000), ('omni/horde/Rocinante-X-12B', 200000, 64000),
    ('omni/kimi-coding/k3', 1048576, 131072), ('omni/kimi-coding/kimi-for-coding', 262144, 65536), ('omni/kimi-coding/kimi-for-coding-highspeed', 262144, 65536), ('omni/kmc/k3', 1048576, 131072),
    ('omni/kmc/kimi-for-coding', 262144, 65536), ('omni/kmc/kimi-for-coding-highspeed', 262144, 65536), ('omni/mcode/mimo-auto', 262144, 131072), ('omni/mimo/mimo-v2.5', 1048576, 131072),
    ('omni/mimo/mimo-v2.5-pro', 1048576, 131072), ('omni/mimo/mimo-v2.5-tts', 1048576, 131072), ('omni/mimo/mimo-v2.5-tts-voiceclone', 1048576, 131072), ('omni/mimo/mimo-v2.5-tts-voicedesign', 1048576, 131072),
    ('omni/no-think/agy/claude-opus-4-6-thinking', 200000, 64000), ('omni/no-think/agy/claude-opus-4-6-thinking-high', 200000, 64000), ('omni/no-think/agy/claude-opus-4-6-thinking-low', 200000, 64000), ('omni/no-think/agy/claude-opus-4-6-thinking-medium', 200000, 64000),
    ('omni/no-think/agy/claude-sonnet-4-6', 1000000, 128000), ('omni/no-think/agy/claude-sonnet-4-6-high', 200000, 64000), ('omni/no-think/agy/claude-sonnet-4-6-low', 200000, 64000), ('omni/no-think/agy/claude-sonnet-4-6-medium', 200000, 64000),
    ('omni/no-think/antigravity/claude-opus-4-6-thinking', 200000, 64000), ('omni/no-think/antigravity/claude-opus-4-6-thinking-high', 200000, 64000), ('omni/no-think/antigravity/claude-opus-4-6-thinking-low', 200000, 64000), ('omni/no-think/antigravity/claude-opus-4-6-thinking-medium', 200000, 64000),
    ('omni/no-think/antigravity/claude-sonnet-4-6', 1000000, 128000), ('omni/no-think/antigravity/claude-sonnet-4-6-high', 200000, 64000), ('omni/no-think/antigravity/claude-sonnet-4-6-low', 200000, 64000), ('omni/no-think/antigravity/claude-sonnet-4-6-medium', 200000, 64000),
    ('omni/oc/big-pickle', 200000, 64000), ('omni/oc/deepseek-v4-flash-free', 1000000, 384000), ('omni/oc/laguna-s-2.1-free', 200000, 32000), ('omni/oc/ling-3.0-flash-free', 128000, 64000),
    ('omni/oc/ling-3.0-tiny-free', 128000, 64000), ('omni/oc/longcat-2.0-free', 200000, 64000), ('omni/oc/mimo-v2.5-free', 1048576, 131072), ('omni/oc/nemotron-3-ultra-free', 128000, 64000),
    ('omni/oc/north-mini-code-free', 200000, 64000), ('omni/opencode/big-pickle', 200000, 64000), ('omni/opencode/deepseek-v4-flash-free', 1000000, 384000), ('omni/opencode-go/deepseek-v4-flash', 1000000, 384000),
    ('omni/opencode-go/deepseek-v4-flash-high', 1000000, 384000), ('omni/opencode-go/deepseek-v4-pro-max', 1000000, 384000), ('omni/opencode-go/glm-5.3', 200000, 128000), ('omni/opencode-go/gpt-5.6-luna', 400000, 128000),
    ('omni/opencode-go/hy3', 262144, 262144), ('omni/opencode-go/hy3-high', 262144, 262144), ('omni/opencode-go/hy3-low', 262144, 262144), ('omni/opencode-go/hy3-none', 262144, 262144),
    ('omni/opencode-go/hy3-preview', 262144, 262144), ('omni/opencode-go/mimo-v2.5', 1048576, 131072), ('omni/opencode-go/mimo-v2.5-pro', 1048576, 131072), ('omni/opencode-go/qwen3.8-max', 1000000, 65536),
    ('omni/opencode/laguna-s-2.1-free', 200000, 32000), ('omni/opencode/ling-3.0-flash-free', 128000, 64000), ('omni/opencode/ling-3.0-tiny-free', 128000, 64000), ('omni/opencode/longcat-2.0-free', 200000, 64000),
    ('omni/opencode/mimo-v2.5-free', 1048576, 131072), ('omni/opencode/nemotron-3-ultra-free', 128000, 64000), ('omni/opencode/north-mini-code-free', 200000, 64000), ('omni/openrouter/black-forest-labs/flux.2-flex', 200000, 64000),
    ('omni/openrouter/black-forest-labs/flux.2-max', 200000, 64000), ('omni/openrouter/black-forest-labs/flux.2-pro', 200000, 64000), ('omni/openrouter/deepgram/nova-3', 200000, 64000), ('omni/openrouter/google/chirp-3', 200000, 64000),
    ('omni/openrouter/google/gemini-3.1-flash-image-preview', 1048576, 64000), ('omni/openrouter/google/gemini-3-pro-image-preview', 1048576, 64000), ('omni/openrouter/microsoft/mai-transcribe-1.5', 200000, 64000), ('omni/openrouter/mistralai/voxtral-mini-transcribe', 128000, 64000),
    ('omni/openrouter/nvidia/parakeet-tdt-0.6b-v3', 200000, 64000), ('omni/openrouter/openai/gpt-4o-mini-transcribe', 128000, 16384), ('omni/openrouter/openai/gpt-4o-transcribe', 128000, 16384), ('omni/openrouter/openai/gpt-5.4-image-2', 200000, 64000),
    ('omni/openrouter/openai/gpt-5-image-mini', 200000, 64000), ('omni/openrouter/openai/whisper-1', 200000, 64000), ('omni/openrouter/openai/whisper-large-v3', 200000, 64000), ('omni/openrouter/openai/whisper-large-v3-turbo', 200000, 64000),
    ('omni/openrouter/qwen/qwen3-asr-flash-2026-02-10', 262144, 64000), ('omni/pepper/pepper-1', 200000, 64000), ('omni/tllm/CLAUDE_4_5_HAIKU', 200000, 64000), ('omni/tllm/CLAUDE_4_6_OPUS', 200000, 64000),
    ('omni/tllm/CLAUDE_4_6_SONNET', 200000, 64000), ('omni/tllm/claude_haiku_3_5', 200000, 64000), ('omni/tllm/claude_opus_4', 200000, 64000), ('omni/tllm/claude_sonnet_4', 200000, 64000),
    ('omni/tllm/deepseek_v4', 128000, 64000), ('omni/tllm/gemini_1_5_flash', 1048576, 64000), ('omni/tllm/gemini_2_0_flash', 1048576, 64000), ('omni/tllm/gemini_2_5_pro', 1048576, 64000),
    ('omni/tllm/gemini_3_flash', 1048576, 64000), ('omni/tllm/gemini_3_pro', 1048576, 64000), ('omni/tllm/GPT_4o', 200000, 64000), ('omni/tllm/GPT_5', 200000, 64000),
    ('omni/tllm/GPT_5_1', 200000, 64000), ('omni/tllm/GPT_5_2', 200000, 64000), ('omni/tllm/GPT_5_3', 200000, 64000), ('omni/tllm/GPT_5_4', 200000, 64000),
    ('omni/tllm/GPT_o3_mini', 200000, 100000), ('omni/tllm/GPT_o4_mini', 200000, 100000), ('omni/tllm/openrouter_deepseek_r1', 128000, 64000), ('omni/tllm/openrouter_gpt_4_o', 200000, 64000),
    ('omni/tllm/openrouter_gpt_4_o_mini', 200000, 64000), ('omni/tllm/openrouter_grok_4', 256000, 64000), ('omni/tllm/sonar-pro', 128000, 64000), ('omni/tllm/together_deepseek_v3', 128000, 64000),
    ('omni/veoaifree-web/seedance', 200000, 64000), ('omni/veoaifree-web/veo', 200000, 64000), ('omni/veo-free/seedance', 200000, 64000), ('omni/veo-free/veo', 200000, 64000),
    ('omni/xiaomi-mimo/mimo-v2.5', 1048576, 131072), ('omni/xiaomi-mimo/mimo-v2.5-pro', 1048576, 131072), ('omni/xiaomi-mimo/mimo-v2.5-tts', 1048576, 131072), ('omni/xiaomi-mimo/mimo-v2.5-tts-voiceclone', 1048576, 131072),
    ('omni/xiaomi-mimo/mimo-v2.5-tts-voicedesign', 1048576, 131072), ('openrouter/google/gemma-4-26b-a4b-it\:free', 128000, 64000), ('openrouter/inclusionai/ling-3.0-flash\:free', 128000, 64000), ('openrouter/openrouter/free', 200000, 64000),
    ('openrouter/poolside/laguna-m.1\:free', 200000, 32000)
) AS v(id, ctx, max_out)
WHERE mc.id = v.id
  AND mc.context_window = 8192
  AND mc.provenance <> 'admin-approved';
