-- 0012: Perf fixes - missing indexes for hot paths
-- S2 backend audit fix: add indexes for catalog lookup and conversations

CREATE INDEX IF NOT EXISTS idx_model_catalog_provider_model_id ON model_catalog(provider_model_id);
CREATE INDEX IF NOT EXISTS idx_model_catalog_provider_model_avail ON model_catalog(provider_model_id, availability) WHERE availability='available';
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_user ON usage_events(user_id);
CREATE INDEX IF NOT EXISTS idx_user_memories_user_active ON user_memories(user_id, active) WHERE active=true;
CREATE INDEX IF NOT EXISTS idx_model_catalog_availability ON model_catalog(availability);

-- Ensure gln etc existing data sane
ANALYZE model_catalog;
ANALYZE conversations;
ANALYZE ledger;
ANALYZE user_memories;
