-- 0006_memory_system.sql
-- Memory system: user_memories table + conversation enhancements

BEGIN;

-- ═══════════════════════════════════════════════════════════════
-- 1. user_memories table
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_memories (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    source      TEXT NOT NULL DEFAULT 'manual',
    tags        TEXT[] DEFAULT '{}',
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_user_memories_user_id   ON user_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_user_memories_category  ON user_memories(category);
CREATE INDEX IF NOT EXISTS idx_user_memories_user_cat  ON user_memories(user_id, category);

-- ═══════════════════════════════════════════════════════════════
-- 2. Enhance conversations table
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS tags         TEXT[] DEFAULT '{}';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS folder      TEXT   DEFAULT NULL;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN DEFAULT false;

COMMIT;
