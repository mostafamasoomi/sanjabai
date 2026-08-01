-- Hermes server product: sell a ready-to-use VPS with the Hermes agent
-- pre-installed, plus a catalog of installable "skills" the user can attach
-- at checkout or later from the dashboard.
--
-- Pricing model: offerings carry the Hetzner EUR cost + margin, never a
-- hardcoded Toman price. GET /hermes/offerings converts live using the
-- eur_to_irt rate (see content.py's exchange-rate machinery, extended by
-- this migration), the same way model_catalog converts usd_*_per_million
-- at read time. Orders and servers snapshot the computed Toman price at
-- purchase time so an exchange-rate move never changes what an existing
-- customer owes.
BEGIN;

CREATE TABLE IF NOT EXISTS hermes_offerings (
    id                 TEXT PRIMARY KEY,
    name_fa            TEXT NOT NULL,
    name_en            TEXT NOT NULL,
    description_fa     TEXT NOT NULL DEFAULT '',
    description_en     TEXT NOT NULL DEFAULT '',
    hetzner_type       TEXT NOT NULL,          -- e.g. 'cx32', 'cax21'
    arch               TEXT NOT NULL DEFAULT 'amd64' CHECK (arch IN ('amd64', 'arm64')),
    vcpu               INTEGER NOT NULL,
    ram_mb             INTEGER NOT NULL,
    disk_gb            INTEGER NOT NULL,
    traffic_tb         INTEGER NOT NULL DEFAULT 20,
    -- Cost basis in EUR (Hetzner's billing currency), never shown to users.
    provider_cost_eur  NUMERIC(8,2) NOT NULL,
    margin_pct         INTEGER NOT NULL DEFAULT 50,
    -- One-time setup/installation fee, already in Toman (human labor, not FX-driven).
    setup_fee_irt      INTEGER NOT NULL DEFAULT 0,
    max_skills         INTEGER NOT NULL DEFAULT 5,
    included_credit    INTEGER NOT NULL DEFAULT 0,
    active             BOOLEAN NOT NULL DEFAULT true,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hermes_offerings_active
    ON hermes_offerings (active, sort_order);

CREATE TABLE IF NOT EXISTS hermes_skill_catalog (
    id                 TEXT PRIMARY KEY,       -- slug, e.g. 'coding', 'news-watch'
    name_fa            TEXT NOT NULL,
    name_en            TEXT NOT NULL,
    description_fa     TEXT NOT NULL DEFAULT '',
    description_en     TEXT NOT NULL DEFAULT '',
    category           TEXT NOT NULL DEFAULT 'general',
    -- Opaque payload the Hermes agent daemon knows how to install; no fixed
    -- schema yet, kept flexible until the on-disk skill format is decided.
    manifest           JSONB NOT NULL DEFAULT '{}',
    -- Drives both server-side validation of order-time config and the
    -- wizard/edit form in the frontend. Example:
    -- {"languages": {"type": "multiselect", "values": ["python","go"], "max": 5}}
    options_schema     JSONB NOT NULL DEFAULT '{}',
    requires_cron      BOOLEAN NOT NULL DEFAULT false,
    active             BOOLEAN NOT NULL DEFAULT true,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hermes_skill_catalog_active
    ON hermes_skill_catalog (active, sort_order);

CREATE TABLE IF NOT EXISTS hermes_orders (
    id                 BIGSERIAL PRIMARY KEY,
    user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    offering_id        TEXT NOT NULL REFERENCES hermes_offerings(id),
    status             TEXT NOT NULL DEFAULT 'pending_payment'
                       CHECK (status IN ('pending_payment', 'paid', 'provisioning', 'active', 'suspended', 'cancelled', 'expired')),
    -- Price locked at order time, all in Toman. Never recomputed later.
    setup_price_irt    INTEGER NOT NULL,
    monthly_price_irt  INTEGER NOT NULL,
    eur_rate_at_order  NUMERIC(12,2),
    priced_at          TIMESTAMPTZ,
    payment_id         INTEGER REFERENCES payments(id),
    requested_config   JSONB NOT NULL DEFAULT '{}',  -- {"skills": [{"skill_id": "...", "options": {...}}]}
    notes              TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at            TIMESTAMPTZ,
    delivered_at       TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hermes_orders_user ON hermes_orders (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hermes_orders_status ON hermes_orders (status);

CREATE TABLE IF NOT EXISTS hermes_servers (
    id                 BIGSERIAL PRIMARY KEY,
    order_id           BIGINT NOT NULL UNIQUE REFERENCES hermes_orders(id),
    user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    offering_id        TEXT NOT NULL REFERENCES hermes_offerings(id),
    hostname           TEXT,
    ip_address         TEXT,
    ssh_port           INTEGER NOT NULL DEFAULT 22,
    region             TEXT,
    status             TEXT NOT NULL DEFAULT 'provisioning'
                       CHECK (status IN ('provisioning', 'active', 'suspended', 'terminated')),
    monthly_price_irt  INTEGER NOT NULL,
    paid_through_at    TIMESTAMPTZ,
    -- Agent daemon auth: same hashing scheme as api_keys (sha256 + pepper),
    -- shown once at provisioning time, never stored in plaintext.
    agent_token_hash   TEXT UNIQUE,
    agent_token_prefix TEXT,
    api_key_id         INTEGER REFERENCES api_keys(id),
    desired_state_version INTEGER NOT NULL DEFAULT 0,
    applied_state_version INTEGER NOT NULL DEFAULT 0,
    last_heartbeat_at  TIMESTAMPTZ,
    agent_version      TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hermes_servers_user ON hermes_servers (user_id);
CREATE INDEX IF NOT EXISTS idx_hermes_servers_status ON hermes_servers (status);
CREATE INDEX IF NOT EXISTS idx_hermes_servers_paid_through
    ON hermes_servers (paid_through_at) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS hermes_server_skills (
    id                 BIGSERIAL PRIMARY KEY,
    server_id          BIGINT NOT NULL REFERENCES hermes_servers(id) ON DELETE CASCADE,
    skill_id           TEXT NOT NULL REFERENCES hermes_skill_catalog(id),
    options            JSONB NOT NULL DEFAULT '{}',
    enabled            BOOLEAN NOT NULL DEFAULT true,
    state              TEXT NOT NULL DEFAULT 'pending'
                       CHECK (state IN ('pending', 'installed', 'failed', 'removing')),
    error              TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (server_id, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_hermes_server_skills_server ON hermes_server_skills (server_id);

CREATE TABLE IF NOT EXISTS hermes_agent_events (
    id                 BIGSERIAL PRIMARY KEY,
    server_id          BIGINT NOT NULL REFERENCES hermes_servers(id) ON DELETE CASCADE,
    event              TEXT NOT NULL,
    detail             JSONB NOT NULL DEFAULT '{}',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hermes_agent_events_server
    ON hermes_agent_events (server_id, created_at DESC);

-- exchange_rate_overrides is read by content.py (_get_exchange_rate /
-- api_exchange_rate) but, like plans/credit_packages/conversations, was
-- never created by a migration -- it only exists because someone created it
-- by hand via psql on deployed environments. Its from_currency/to_currency
-- columns already generalize to EUR (no schema change needed for the Hermes
-- EUR rate); we just make sure the table exists so a fresh environment
-- doesn't 500 the first time this or content.py queries it.
CREATE TABLE IF NOT EXISTS exchange_rate_overrides (
    id             BIGSERIAL PRIMARY KEY,
    from_currency  TEXT NOT NULL,
    to_currency    TEXT NOT NULL,
    rate           NUMERIC(14,2) NOT NULL,
    active         BOOLEAN NOT NULL DEFAULT true,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exchange_rate_overrides_lookup
    ON exchange_rate_overrides (from_currency, to_currency, active);

-- Seed offerings from Hetzner's published price list (checked August 2026,
-- post the June 2026 price increase). These are a starting point only --
-- Hetzner pricing varies by region and changes over time, so provider_cost_eur
-- and margin_pct must be reviewed/edited from the admin panel before this
-- product goes live, and again whenever Hetzner's price list changes. No
-- redeploy or migration is needed to adjust them.
INSERT INTO hermes_offerings (id, name_fa, name_en, description_fa, description_en, hetzner_type, arch, vcpu, ram_mb, disk_gb, traffic_tb, provider_cost_eur, margin_pct, setup_fee_irt, max_skills, included_credit, active, sort_order) VALUES
    ('hermes-starter',      'هرمس استارتر',        'Hermes Starter',      'مناسب یک اسکیل سبک مثل رصد اخبار', 'Good for one light skill such as news monitoring', 'cx22',  'amd64', 2,  4096,  40,  20, 4.35,  50, 0, 2, 0, true, 10),
    ('hermes-standard',     'هرمس استاندارد',       'Hermes Standard',     'حداقل توصیه‌شده برای اجرای هرمس',   'Recommended minimum for running Hermes',           'cx32',  'amd64', 4,  8192,  80,  20, 6.80,  50, 0, 5, 0, true, 20),
    ('hermes-pro',          'هرمس پرو',             'Hermes Pro',          'برای چند اسکیل هم‌زمان و بار سنگین‌تر', 'For several concurrent skills and heavier load',   'cx42',  'amd64', 8,  16384, 160, 20, 16.40, 50, 0, 10, 0, true, 30),
    ('hermes-max',          'هرمس مکس',             'Hermes Max',          'بیشترین ظرفیت برای تیم‌ها',          'Maximum capacity for teams',                        'cx52',  'amd64', 16, 32768, 320, 20, 32.80, 50, 0, 20, 0, true, 40),
    ('hermes-standard-arm', 'هرمس استاندارد (ARM)', 'Hermes Standard ARM', 'گزینه‌ی ارزان‌تر روی معماری ARM',    'Cheaper alternative on ARM architecture',           'cax21', 'arm64', 4,  8192,  80,  20, 7.99,  50, 0, 5, 0, true, 25)
ON CONFLICT (id) DO NOTHING;

INSERT INTO hermes_skill_catalog (id, name_fa, name_en, description_fa, description_en, category, manifest, options_schema, requires_cron, active, sort_order) VALUES
    ('coding',     'برنامه‌نویسی',   'Coding',     'دستیار کدنویسی با زبان‌های انتخابی', 'Coding assistant with selected languages', 'development', '{}', '{"languages": {"type": "multiselect", "values": ["python", "javascript", "typescript", "go", "rust", "java", "csharp", "php"], "max": 5, "default": ["python"]}}', false, true, 10),
    ('news-watch',  'رصد اخبار',      'News Watch', 'رصد و خلاصه‌سازی دوره‌ای اخبار موضوعات انتخابی', 'Periodic monitoring and summarizing of chosen topics', 'monitoring', '{}', '{"topics": {"type": "tags", "max": 10}, "schedule": {"type": "cron", "default": "0 9 * * *"}}', true, true, 20),
    ('research',    'پژوهش',          'Research',   'جمع‌آوری و جمع‌بندی منابع درباره‌ی یک موضوع', 'Gathering and summarizing sources on a topic', 'research', '{}', '{"topics": {"type": "tags", "max": 10}}', false, true, 30)
ON CONFLICT (id) DO NOTHING;

COMMIT;
