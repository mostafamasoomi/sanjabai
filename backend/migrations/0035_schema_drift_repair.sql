-- 0035_schema_drift_repair.sql
--
-- Repairs four live 500s (GET /about, /assistants, /admin/features,
-- /admin/discounts, /content/features, /content/discounts) caused by
-- ORM-vs-database drift in backend/models.py -- the exact same class of bug
-- migration 0033 fixed for proxy_config (a SELECT naming a column Postgres
-- doesn't have raises UndefinedColumn, which is why these were 500s and not
-- empty lists).
--
-- All three drifted tables touched below (features, discounts, about) are
-- verified EMPTY in production (0 rows each), so every destructive step
-- here (DROP COLUMN, RENAME TABLE) loses no data. That emptiness is the
-- justification for choosing "make the database match the ORM" rather than
-- the reverse in every case below.
--
-- ── features: ORM is right, table is missing three columns ─────────────
-- models.py's Feature declares (title, description, icon, active,
-- order_idx, updated_at). migrations/0001_baseline.sql only ever created
-- (title, body, order_idx, updated_at) -- a generic landing-content-block
-- shape. content.py's GET /content/features and admin.py's
-- /admin/features CRUD both already read and write description/icon/active
-- through the ORM, and backend/init_db.sql's seed data (INSERT INTO
-- features (title, description, icon, order_idx, active, ...)) and the
-- frontend's FeatureRow (frontend/app/admin/AdminPanel.tsx) agree with the
-- ORM shape too -- the baseline table is the stale side. `body` is not
-- read or written anywhere any more, so it is dropped rather than kept as
-- dead weight.
ALTER TABLE features ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';

ALTER TABLE features ADD COLUMN IF NOT EXISTS icon TEXT NOT NULL DEFAULT 'star';

ALTER TABLE features ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE features DROP COLUMN IF EXISTS body;

-- ── discounts: two different features collided on one table name ───────
-- models.py's Discount (code, percent, active, expires_at) describes a
-- discount-code feature. migrations/0001_baseline.sql's discounts table
-- (title, body, order_idx) describes a landing-page content block -- the
-- same shape as the OLD features table above, just never renamed.
--
-- The discount-code shape is what the rest of the codebase actually uses:
-- content.py's GET /content/discounts reads row.code/row.percent,
-- admin.py's /admin/discounts CRUD reads and writes
-- code/percent/active/expires_at, the frontend's DiscountRow and
-- DiscountsSection (frontend/app/admin/) only ever render code/percent/
-- active, and the standalone admin/app.py (a separate reference
-- implementation of the same product) already issues raw SQL against
-- exactly this shape (SELECT id, code, percent, active, expires_at,
-- updated_at FROM discounts) and backend/init_db.sql / init_db.py both
-- seed discount CODES (WELCOME10, SUMMER20) through it. Nothing anywhere
-- reads or writes discounts.title/body/order_idx as a content block --
-- that feature was never wired to a serving endpoint, so those columns are
-- dropped rather than kept.
--
-- discounts.title is NOT NULL with no default (see the bug brief): simply
-- adding the ORM's columns would still leave an ORM insert broken on that
-- leftover NOT NULL column. Dropping title/body/order_idx outright (the
-- table is empty, so there is no data to preserve) removes the trap
-- instead of working around it.
ALTER TABLE discounts ADD COLUMN IF NOT EXISTS code TEXT NOT NULL;

ALTER TABLE discounts ADD COLUMN IF NOT EXISTS percent INT NOT NULL DEFAULT 10;

ALTER TABLE discounts ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE discounts ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

ALTER TABLE discounts DROP COLUMN IF EXISTS title;

ALTER TABLE discounts DROP COLUMN IF EXISTS body;

ALTER TABLE discounts DROP COLUMN IF EXISTS order_idx;

-- models.py's Discount.code is unique=True. Postgres has no ADD CONSTRAINT
-- IF NOT EXISTS, and a bare ADD CONSTRAINT is not idempotent (documented in
-- migrations/0030_markup_pct.sql and 0032_image_pricing.sql after it broke
-- a re-run there) -- DROP CONSTRAINT IF EXISTS then ADD is the idempotent
-- house pattern, used as-is here.
ALTER TABLE discounts DROP CONSTRAINT IF EXISTS discounts_code_key;

ALTER TABLE discounts ADD CONSTRAINT discounts_code_key UNIQUE (code);

-- ── about: right columns, wrong table name ──────────────────────────────
-- models.py's AboutContent already declares exactly the columns the live
-- `about` table has (id, title, body, updated_at) -- this is a pure
-- naming drift, not a column drift. __tablename__ is 'about_content', and
-- content.py's GET /about and admin.py's POST /admin/about both query
-- through AboutContent.__table__, so they ask Postgres for a table named
-- about_content, which has never existed -- only `about` (created by
-- migrations/0001_baseline.sql) does. backend/init_db.sql independently
-- agrees the intended name is about_content (its seed does
-- "INSERT INTO about_content ..."), so the table name is the stale side,
-- not the ORM.
--
-- Postgres supports IF EXISTS on ALTER TABLE ... RENAME TO, which is what
-- makes this idempotent: the first run renames the table; every run after
-- that finds no table named `about` left to rename and skips harmlessly
-- (a NOTICE, not an error).
ALTER TABLE IF EXISTS about RENAME TO about_content;

-- Safety net for a schema that somehow has neither table (should not
-- happen given migrations always run in order after the baseline, but this
-- keeps the migration self-sufficient rather than depending on that
-- ordering assumption). Naturally idempotent, and a no-op once the rename
-- above has already run.
CREATE TABLE IF NOT EXISTS about_content (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    title TEXT,
    body TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── assistants: table simply does not exist ─────────────────────────────
-- models.py's Assistant model is fully formed (assistants.py already reads
-- and writes through it) but migrations/0001_baseline.sql never created a
-- backing table -- every query against it 500s with "relation assistants
-- does not exist". Columns and the user_id foreign key/index below match
-- the ORM's Mapped[...] declarations and defaults exactly, the same way
-- migration 0033 chose proxy_config's backfill defaults to match ORM
-- defaults exactly.
CREATE TABLE IF NOT EXISTS assistants (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL DEFAULT 'New Assistant',
    description TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT 'chat',
    is_public BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_assistants_user ON assistants(user_id);

-- Idempotency note for the whole file: every ADD COLUMN/CREATE TABLE/
-- CREATE INDEX above uses its IF NOT EXISTS form (naturally idempotent in
-- Postgres); the one named constraint uses DROP-then-ADD; the one RENAME
-- uses ALTER TABLE IF EXISTS. Running this file twice succeeds both times.
--
-- No DO $$ ... $$ block anywhere in this file: migrate.py's split_sql()
-- splits on every top-level semicolon and does not understand
-- dollar-quoting, so a PL/pgSQL block would be shredded into invalid
-- fragments.
--
-- Every colon above is either absent from prose or immediately followed by
-- whitespace, never by a word character -- migrate.py hands each split
-- statement to SQLAlchemy's text(), which reads a bare colon directly
-- followed by an identifier as a bind parameter and refuses the whole
-- statement even inside a comment (this is what made migration 0029
-- unrunnable).
