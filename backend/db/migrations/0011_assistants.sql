-- Create assistants table for custom AI assistants
CREATE TABLE IF NOT EXISTS assistants (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL DEFAULT 'New Assistant',
    description TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT 'chat',
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_assistants_user ON assistants(user_id);
CREATE INDEX IF NOT EXISTS idx_assistants_public ON assistants(is_public) WHERE is_public = TRUE;
