-- 0047_exchange_sources.sql
--
-- Owner's ask (2026-08-25, Persian, see NEXT-SESSION.md): pull the USD to
-- Toman rate from Bonbast.com alongside tgju.org, and leave room for the
-- admin to add another reference site from the panel later without a
-- deploy. This migration adds exactly the storage for that -- the Python
-- side (services/exchange_sources.py, backend/content.py,
-- backend/exchange_rate_admin.py) is a separate, already-reviewed change.
--
-- ── Scope decision -- why this table does NOT also hold tgju/er_api/hardcoded ──
-- content.py's existing 4-tier resolver (db_override -> tgju -> er_api ->
-- hardcoded_fallback) is covered by a locked regression suite
-- (tests/test_exchange_rate_source.py) that patches
-- content._fetch_tgju_rate directly and asserts the exact tier order and
-- source strings. Moving tgju/er_api/hardcoded into this table and
-- dispatching them generically would have required rewriting that
-- resolver and risked silently changing which tier wins in production.
-- So this table holds only what is genuinely new: Bonbast.com (a real
-- built-in fetcher, kind='bonbast', is_builtin=true, not deletable) and
-- any future admin-added source (kind='custom_regex'). Both are tried, in
-- priority order, as an extra rung inserted between tgju and er_api --
-- see content.py's _compute_exchange_rate(). tgju/er_api/hardcoded_fallback
-- remain pure code, unchanged, and are surfaced to the admin panel as
-- read-only informational rows by the API layer, not by this table.
--
-- ── Trust boundary -- read before adding a new kind ─────────────────────
-- 'custom_regex' is a DECLARATIVE extractor only: an admin supplies a URL
-- and a regex; the regex is applied to the fetched response text with a
-- length cap and a wall-clock timeout (services/exchange_sources.py's
-- _bounded_search). There is no 'eval', 'exec', or arbitrary-expression
-- kind, and none should ever be added -- a URL plus an extraction rule is
-- already remote-content parsing, and turning it into code execution would
-- let anyone with admin-panel access (today: the owner only, via
-- admin_required) pivot from "read a number off a web page" to "run
-- arbitrary code on the production box".
--
-- ── Idempotency ──────────────────────────────────────────────────────────
-- No DO $$ ... $$ block -- migrate.py's split_sql() splits on every
-- top-level semicolon and does not understand dollar-quoting (see
-- 0030_markup_pct.sql for the same note). Postgres has no
-- "ADD CONSTRAINT IF NOT EXISTS", so every CHECK constraint below is
-- dropped first, then added, as two separate idempotent statements. Seed
-- rows use ON CONFLICT (source_key) DO NOTHING so re-running this file, or
-- an admin who has since edited the seeded Bonbast row, is never reset.

CREATE TABLE IF NOT EXISTS exchange_rate_sources (
    id             serial PRIMARY KEY,
    source_key     text NOT NULL,
    display_name   text NOT NULL,
    kind           text NOT NULL,
    url            text,
    unit           text NOT NULL DEFAULT 'toman',
    extract_regex  text,
    enabled        boolean NOT NULL DEFAULT true,
    priority       integer NOT NULL DEFAULT 100,
    timeout_s      numeric NOT NULL DEFAULT 5,
    is_builtin     boolean NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS source_key text;
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS display_name text;
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS kind text;
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS url text;
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS unit text DEFAULT 'toman';
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS extract_regex text;
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS enabled boolean DEFAULT true;
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS priority integer DEFAULT 100;
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS timeout_s numeric DEFAULT 5;
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS is_builtin boolean DEFAULT false;
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE exchange_rate_sources ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

DROP INDEX IF EXISTS ux_exchange_rate_sources_source_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_exchange_rate_sources_source_key ON exchange_rate_sources (source_key);

DROP INDEX IF EXISTS ix_exchange_rate_sources_enabled_priority;
CREATE INDEX IF NOT EXISTS ix_exchange_rate_sources_enabled_priority ON exchange_rate_sources (enabled, priority);

-- kind is a closed set on purpose -- see the trust-boundary note above. A
-- future built-in fetcher (a new "kind") needs a new migration to extend
-- this, same as any other append-only change in this repo.
ALTER TABLE exchange_rate_sources DROP CONSTRAINT IF EXISTS exchange_rate_sources_kind_chk;
ALTER TABLE exchange_rate_sources
    ADD CONSTRAINT exchange_rate_sources_kind_chk
    CHECK (kind IN ('bonbast', 'custom_regex'));

ALTER TABLE exchange_rate_sources DROP CONSTRAINT IF EXISTS exchange_rate_sources_unit_chk;
ALTER TABLE exchange_rate_sources
    ADD CONSTRAINT exchange_rate_sources_unit_chk
    CHECK (unit IN ('toman', 'rial'));

-- A custom_regex row is meaningless without both a URL and an extraction
-- rule; a bonbast row supplies neither (its fetch logic is fixed Python
-- code, not database-driven) so the check only binds the custom kind.
ALTER TABLE exchange_rate_sources DROP CONSTRAINT IF EXISTS exchange_rate_sources_custom_fields_chk;
ALTER TABLE exchange_rate_sources
    ADD CONSTRAINT exchange_rate_sources_custom_fields_chk
    CHECK (kind <> 'custom_regex' OR (url IS NOT NULL AND extract_regex IS NOT NULL));

-- Defense in depth alongside the app-layer length checks in
-- services/exchange_sources.py (validate_source_url / the 200-char pattern
-- cap) -- a hostile or corrupted row can never carry an unbounded string
-- into the fetch path even if the app-layer check is ever bypassed.
ALTER TABLE exchange_rate_sources DROP CONSTRAINT IF EXISTS exchange_rate_sources_url_len_chk;
ALTER TABLE exchange_rate_sources
    ADD CONSTRAINT exchange_rate_sources_url_len_chk
    CHECK (url IS NULL OR char_length(url) <= 2048);

ALTER TABLE exchange_rate_sources DROP CONSTRAINT IF EXISTS exchange_rate_sources_regex_len_chk;
ALTER TABLE exchange_rate_sources
    ADD CONSTRAINT exchange_rate_sources_regex_len_chk
    CHECK (extract_regex IS NULL OR char_length(extract_regex) <= 200);

ALTER TABLE exchange_rate_sources DROP CONSTRAINT IF EXISTS exchange_rate_sources_priority_chk;
ALTER TABLE exchange_rate_sources
    ADD CONSTRAINT exchange_rate_sources_priority_chk
    CHECK (priority > 0);

-- Capped well under the Next.js proxy's known 30s ceiling (see the
-- nextjs-proxy-30s-cliff note) -- a single misconfigured source must never
-- be able to stall the whole exchange-rate resolution for that long.
ALTER TABLE exchange_rate_sources DROP CONSTRAINT IF EXISTS exchange_rate_sources_timeout_chk;
ALTER TABLE exchange_rate_sources
    ADD CONSTRAINT exchange_rate_sources_timeout_chk
    CHECK (timeout_s > 0 AND timeout_s <= 10);

-- Seed the one real built-in this migration adds: Bonbast.com, tried right
-- after tgju.org and before open.er-api.com (see content.py). Bonbast
-- publishes Toman directly (confirmed against the live site 2026-08-25 --
-- see the coordinator's report), so unit='toman', matching the fixed
-- Python fetcher in services/exchange_sources.py which never reads this
-- row's (absent) url/extract_regex -- they are populated here purely for
-- admin-panel display.
INSERT INTO exchange_rate_sources
    (source_key, display_name, kind, url, unit, extract_regex, enabled, priority, timeout_s, is_builtin)
VALUES
    ('bonbast', 'Bonbast.com', 'bonbast', 'https://bonbast.com/', 'toman', NULL, true, 20, 8, true)
ON CONFLICT (source_key) DO NOTHING;

-- The flat Toman markup added to the USD->IRT rate
-- (content.py's USD_IRT_FLAT_MARKUP) becomes admin-editable here, stored the
-- same way migration 0030 stored global_markup_pct: a row in the existing
-- generic app_setting table (key TEXT PRIMARY KEY, value JSONB NOT NULL),
-- not a new table. Seeded at 2000 -- today's real production value (no
-- USD_IRT_FLAT_MARKUP env var is set on this box; the code default is
-- already 2000), so applying this migration is a strict no-op on every
-- displayed and billed price, exactly like 0030's seed was for the
-- percentage markup.
CREATE TABLE IF NOT EXISTS app_setting (
    key text PRIMARY KEY,
    value jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app_setting (key, value)
VALUES ('usd_irt_flat_markup_toman', '2000')
ON CONFLICT (key) DO NOTHING;
