-- 0022_provider_config.sql
-- Phase 4: DB-driven providers

CREATE TABLE IF NOT EXISTS provider (
    name VARCHAR(64) PRIMARY KEY,
    display_name VARCHAR(128) NOT NULL,
    base_url VARCHAR(256) NOT NULL,
    api_key_env VARCHAR(128) NOT NULL,
    health_path VARCHAR(256),
    adapter VARCHAR(32) DEFAULT 'openai',
    enabled BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 0,
    timeout_s INTEGER DEFAULT 60,
    is_default_chat BOOLEAN DEFAULT false
);

-- Seed existing providers based on current env usage so they are instantly available
INSERT INTO provider (name, display_name, base_url, api_key_env, adapter, enabled, is_default_chat)
VALUES ('litellm', 'LiteLLM Proxy', 'http://127.0.0.1:4000', 'LITELLM_API_KEY', 'openai', true, true)
ON CONFLICT (name) DO NOTHING;

INSERT INTO provider (name, display_name, base_url, api_key_env, health_path, adapter, enabled, priority)
VALUES ('ninerouter', '9Router', 'https://api.9router.sanjabai.ir', 'NINEROUTER_API_KEY', '/health', 'openai', true, 1)
ON CONFLICT (name) DO NOTHING;
