-- 0007: Skills Marketplace
-- Skill templates for the marketplace

CREATE TABLE IF NOT EXISTS skill_templates (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    title_fa TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    description_fa TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    prompt_template TEXT NOT NULL,
    variables JSONB DEFAULT '[]',
    default_model TEXT DEFAULT '',
    is_public BOOLEAN NOT NULL DEFAULT false,
    is_featured BOOLEAN NOT NULL DEFAULT false,
    usage_count INTEGER NOT NULL DEFAULT 0,
    rating_sum INTEGER NOT NULL DEFAULT 0,
    rating_count INTEGER NOT NULL DEFAULT 0,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_skill_templates_category ON skill_templates(category) WHERE is_public = true;
CREATE INDEX IF NOT EXISTS idx_skill_templates_user ON skill_templates(user_id);
CREATE INDEX IF NOT EXISTS idx_skill_templates_featured ON skill_templates(is_featured) WHERE is_public = true;

CREATE TABLE IF NOT EXISTS skill_template_ratings (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES skill_templates(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(template_id, user_id)
);
