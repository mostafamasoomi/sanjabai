-- 0008: Skill templates, ratings, scheduled tasks, task executions
CREATE TABLE IF NOT EXISTS skill_templates (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title TEXT NOT NULL,
    title_fa TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    description_fa TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    prompt_template TEXT NOT NULL,
    variables JSONB DEFAULT '[]',
    default_model TEXT NOT NULL DEFAULT '',
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    is_featured BOOLEAN NOT NULL DEFAULT FALSE,
    usage_count INTEGER NOT NULL DEFAULT 0,
    rating_sum INTEGER NOT NULL DEFAULT 0,
    rating_count INTEGER NOT NULL DEFAULT 0,
    tags JSONB DEFAULT '[]',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_skill_templates_user ON skill_templates(user_id);

CREATE TABLE IF NOT EXISTS skill_template_ratings (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES skill_templates(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    rating INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'mimo-v2.5',
    cron_expression TEXT NOT NULL DEFAULT '0 9 * * *',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at TIMESTAMP WITHOUT TIME ZONE,
    next_run_at TIMESTAMP WITHOUT TIME ZONE,
    run_count INTEGER NOT NULL DEFAULT 0,
    last_result TEXT,
    delivery_channel TEXT NOT NULL DEFAULT 'dashboard',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_user ON scheduled_tasks(user_id);

CREATE TABLE IF NOT EXISTS task_executions (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES scheduled_tasks(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    cost_toman INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
