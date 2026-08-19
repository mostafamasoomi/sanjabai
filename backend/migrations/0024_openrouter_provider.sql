-- 0024_openrouter_provider.sql
-- Register OpenRouter as a configurable provider row. Disabled by default so
-- nothing changes at runtime until an OPENROUTER_API_KEY is supplied and the
-- row is explicitly enabled.

INSERT INTO provider (name, display_name, base_url, api_key_env, adapter, enabled, priority)
VALUES ('openrouter', 'OpenRouter', 'https://openrouter.ai/api/v1', 'OPENROUTER_API_KEY', 'openai', false, 2)
ON CONFLICT (name) DO NOTHING;
