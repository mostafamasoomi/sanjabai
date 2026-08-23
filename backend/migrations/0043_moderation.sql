-- Phase J — content safety. Two tables + six settings rows.
--
-- Until this migration the product inspected user messages nowhere: a grep
-- of the whole backend for moderat|abuse|blocklist|banned_word|nsfw
-- returned two hits (auth.py's "prevent abuse" comment and watchdog.py's
-- "Possible abuse or bot" alert string), neither of them moderation.
-- Nothing read a message, nothing was logged, no alert fired.
--
-- Read backend/services/moderation.py first -- it is the only writer of
-- moderation_event and the only reader of moderation_rule on the hot path;
-- backend/admin_moderation.py is the only writer of moderation_rule.
--
-- ── RETENTION POLICY (enforced, not aspirational) ──────────────────────────
-- moderation_event is the most sensitive data this product stores: it is a
-- record of what individual users asked for. Three rules, all enforced in
-- code, not merely written down here:
--
--   1. NEVER the whole message. Only `snippet`, a window of at most 120
--      characters around what actually matched, taken from the NORMALIZED
--      text. Enforced twice in services/moderation.py -- once where the
--      window is cut (_match) and again at the INSERT (_record_event), so
--      a future caller cannot widen it by accident. TEXT rather than
--      VARCHAR(120) deliberately: a length ceiling that lives only in the
--      column type would make an over-long snippet a 500 on the chat hot
--      path, and this table must never be able to break chat.
--   2. Rows older than `moderation_retention_days` (seeded at 90) are
--      DELETED. services/moderation.py::_record_event runs that DELETE at
--      most once an hour (guarded by the Redis key moderation:purge:lock)
--      on the already-rare flag/block path, so retention costs a clean
--      request nothing and needs no cron that could silently stop running.
--      Lower the setting and the next purge honours it; there is no
--      separate job to remember.
--   3. Clean requests write NOTHING. Only flag/block decisions and
--      detector failures produce a row, so this table is a record of
--      incidents, not a transcript of the site.
--
-- Deleting a user or a rule must not destroy the incident history, and an
-- incident must not pin a user row -- hence ON DELETE SET NULL on both FKs
-- and a NULLable user_id.
--
-- APPEND-ONLY: like every migration in this directory, never edit this file
-- after the session that added it. A later correction is 0044+.

CREATE TABLE IF NOT EXISTS moderation_rule (
    id BIGSERIAL PRIMARY KEY,
    -- A Python `re` pattern, matched against the three normalized forms
    -- produced by services/moderation.py::normalize_variants. UNIQUE so the
    -- seed below is idempotent and so the panel cannot accumulate
    -- duplicates. Length is capped at 200 chars by
    -- admin_moderation.validate_pattern, which also rejects backreferences
    -- and nested quantifiers and times a real run against an adversarial
    -- subject -- an admin-supplied regex runs on the chat hot path, so a
    -- catastrophic-backtracking pattern is a self-inflicted DoS.
    pattern TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT 'other',
    -- low | medium | high | critical. A rule only BLOCKS when its severity
    -- reaches moderation_block_severity (seeded 'high'); anything below
    -- that flags and alerts without stopping the request.
    severity TEXT NOT NULL DEFAULT 'medium',
    enabled BOOLEAN NOT NULL DEFAULT true,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS moderation_event (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    -- No FK and NULL in practice today: the four chat routes screen the
    -- request BEFORE a conversation row exists, and ChatRequest carries no
    -- conversation id at all. The column exists because the frozen admin
    -- API exposes it; services/moderation.py does not fill it with a guess.
    conversation_id BIGINT,
    category TEXT NOT NULL DEFAULT 'other',
    severity TEXT NOT NULL DEFAULT 'low',
    rule_id BIGINT REFERENCES moderation_rule(id) ON DELETE SET NULL,
    -- <=120 chars, normalized, window around the match. See RETENTION above.
    snippet TEXT NOT NULL DEFAULT '',
    -- allow | flag | block. 'allow' rows are ONLY written for a detector
    -- failure (fail-safe: the request passed, but we want to know), never
    -- for a clean request.
    decision TEXT NOT NULL DEFAULT 'flag',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The admin list is "newest first, optionally filtered"; the per-user page
-- and the risk score are "this user's recent rows".
CREATE INDEX IF NOT EXISTS idx_moderation_event_created
    ON moderation_event(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_moderation_event_user
    ON moderation_event(user_id, created_at DESC);

-- ── Settings (app_setting, JSONB values) ───────────────────────────────────
-- app_setting already exists (migration 0036) and already holds
-- global_markup_pct: a generic key/value store, so these are rows, not a
-- third table. services/moderation.py reads all six as ONE Redis-cached
-- blob (cache:moderation:config, 60s), which is the single added cost a
-- harmless message pays.
--
--   moderation_enabled            master switch.
--   moderation_block_severity     minimum rule severity that blocks rather
--                                 than merely flags.
--   moderation_model_sample_rate  fraction of CLEAN messages that also get
--                                 the model pass. Seeded 0: a model call on
--                                 every message would roughly double the
--                                 cost of every request, and no request may
--                                 be loss-making.
--   moderation_model_on_hit       run the model pass when a rule hits (rare,
--                                 so cheap). The model can only DOWNGRADE a
--                                 block to a flag; it can never block on its
--                                 own, so every block has a rule behind it.
--   moderation_model              which model the pass uses. Seeded ''
--                                 (empty) = layer 2 inert until an admin
--                                 names a model, so this migration cannot
--                                 start spending money on its own.
--   moderation_retention_days     see RETENTION above.
INSERT INTO app_setting (key, value, updated_at) VALUES
    ('moderation_enabled',           'true'::jsonb,   now()),
    ('moderation_block_severity',    '"high"'::jsonb, now()),
    ('moderation_model_sample_rate', '0'::jsonb,      now()),
    ('moderation_model_on_hit',      'true'::jsonb,   now()),
    ('moderation_model',             '""'::jsonb,     now()),
    ('moderation_retention_days',    '90'::jsonb,     now())
ON CONFLICT (key) DO NOTHING;

-- ── Starter rules ──────────────────────────────────────────────────────────
-- Persian first, with the finglish spellings, because an English word list
-- scores approximately zero on this product. Patterns are written against
-- the NORMALIZED text, so they can assume: lowercase, Persian ی/ک/ه (never
-- the Arabic ي/ك/ة), ASCII digits, no ZWNJ, no harakat -- plus they are
-- additionally tried against a leet-folded form (s3x -> sex) and a
-- separator-stripped form (س.ک.س -> سکس). Do NOT re-encode those variants
-- into the pattern itself.
--
-- Honest about what this list is: this file is committed to a PUBLIC
-- repository, so these patterns are public and therefore gameable. It is a
-- floor that makes the feature real on day one, not a ceiling -- the rules
-- an admin adds through /admin/moderation/rules live only in the database
-- and are the ones that actually stay ahead. Deliberately narrow: each
-- pattern wants an intent word ("how to make", "buy") near the subject, so
-- that asking a news or history question does not trip it. Only the two
-- highest-harm categories are seeded as 'critical'; the rest flag or block
-- at the seeded 'high' threshold, and the last one is 'medium' on purpose
-- (adult content is a flag-and-watch, not a hard block).
--
-- ── PERSIAN WORD ORDER (why every category has TWO rows) ───────────────────
-- The first draft of this list was written in ENGLISH word order -- intent
-- first, object second, and only the NOUN form of the intent
-- ((خرید|فروش|تهیه), (ساخت|درست کردن|سنتز)). Persian is verb-final and
-- speakers use verb forms, so the most ordinary phrasing of every one of
-- these requests slipped straight through. Measured against real phrasings:
--   چطور بمب درست کنم          MISS  (object first, verb form درست کنم)
--   از کجا اسلحه بخرم           MISS  (object first, verb form بخرم)
--   میخوام کلت بخرم             MISS
--   برام یه باج افزار بنویس     MISS  (object first, verb form بنویس)
--   چطور اینستاگرام یکی رو هک کنم MISS
--   چطوری شیشه بپزم            MISS
-- 6 of 8 harmful probes. A rule list that only fires on phrasing nobody
-- uses is exactly the failure this phase exists to prevent, so every
-- category below now ships BOTH directions -- the shape the two csam rows
-- already used -- and every intent alternation carries the verb stems
-- (بخر، بپز، بنویس، بساز، درست کن، هک) next to the noun forms.
--
-- TWO ROWS, NOT ONE ORDER-INDEPENDENT ROW, for two reasons: a combined
-- `(I..O|O..I)` pattern doubles both alternations and blows past the
-- 200-character ceiling admin_moderation.validate_pattern enforces (so an
-- admin could no longer re-save the rule after editing one word), and a
-- lookahead form `(?=.*I)(?=.*O)` would drop the [^\n]{0,25} proximity
-- window that is the only thing keeping "درباره جنگ جهانی دوم و اسلحه های
-- اون دوره بنویس" out of the weapons rule.
--
-- PATTERNS ARE MATCHED AGAINST NORMALIZED TEXT, so: ZWNJ is already gone
-- (باج‌افزار arrives as باجافزار -- hence `باج ?افزار`, never a bare space),
-- ئ/ي fold to ی (هروئین arrives as هرویین) and everything is lowercase.
-- The reverse rows are deliberately NARROWER than the forward ones where a
-- word is ambiguous: the drugs reverse row takes only cooking verbs
-- (بپز|میپز|پخت|سنتز) and not بساز/تولید, because شیشه also means "glass"
-- and «شیشه ماشین رو بسازم» must not be a block.
--
-- The benign counter-set every change to this list is re-checked against:
-- «تاریخچه بمب اتم رو توضیح بده», «درباره جنگ جهانی دوم و اسلحه های اون
-- دوره بنویس», «چطور یک وب اپلیکیشن امن بنویسم», «سلام حالت چطوره», plus
-- tests/test_admin_moderation.py::TestSeededRulesAreSafeAndReal.
INSERT INTO moderation_rule (pattern, category, severity, notes) VALUES
    -- ── csam (critical) — already bidirectional ────────────────────────────
    ('(کودک|بچه|نوجوان|خردسال|kudak|bacheh?)[^\n]{0,25}(سکس|برهنه|پورن|تجاوز|sex|porn)',
     'csam', 'critical', 'کودک‌آزاری جنسی — بالاترین اولویت'),
    ('(سکس|برهنه|پورن|تجاوز|sex|porn)[^\n]{0,25}(کودک|بچه|نوجوان|خردسال|kudak)',
     'csam', 'critical', 'همان قاعده، با ترتیب واژه‌های برعکس'),

    -- ── weapons: making explosives, both word orders ──────────────────────
    ('(ساخت|بساز|میساز|درست ?کن|سنتز|فرمول|تولید|sakht|besaz|dorost)[^\n]{0,25}(بمب|مواد منفجره|نارنجک|تی ?ان ?تی|c4|tnt|bomb)',
     'weapons', 'high', 'آموزش ساخت مواد منفجره — نیت پیش از موضوع'),
    ('(بمب|مواد منفجره|نارنجک|تی ?ان ?تی|c4|tnt|bomb)[^\n]{0,25}(ساخت|بساز|میساز|درست ?کن|سنتز|فرمول|تولید|besaz|dorost)',
     'weapons', 'high', 'همان قاعده با ترتیب فارسی: «چطور بمب درست کنم»'),

    -- ── weapons: buying firearms, both word orders ────────────────────────
    ('(خرید|بخر|میخر|فروش|میفروش|تهیه|kharid|bekhar|forush)[^\n]{0,25}(اسلحه|کلت|کلاشنیکف|تفنگ جنگی|aslahe)',
     'weapons', 'high', 'خرید و فروش سلاح گرم — نیت پیش از موضوع'),
    ('(اسلحه|کلت|کلاشنیکف|تفنگ جنگی|aslahe)[^\n]{0,25}(بخر|میخر|خرید|بفروش|میفروش|فروش|bekhar|forush)',
     'weapons', 'high', 'همان قاعده با ترتیب فارسی: «از کجا اسلحه بخرم»'),

    -- ── drugs: producing narcotics, both word orders ──────────────────────
    ('(ساخت|بساز|سنتز|تولید|پخت|بپز|میپز|sakht|sentez)[^\n]{0,25}(شیشه|مت ?امفتامین|هرویین|کراک|methamphetamine|heroin)',
     'drugs', 'high', 'آموزش تولید مواد مخدر — نیت پیش از موضوع'),
    ('(شیشه|مت ?امفتامین|هرویین|کراک|methamphetamine|heroin)[^\n]{0,25}(بپز|میپز|پخت|سنتز|sentez)',
     'drugs', 'high', 'ترتیب فارسی «شیشه بپزم». عمداً فقط افعال پخت: «شیشه» معنی دوم دارد'),

    -- ── self harm (unchanged: the Persian phrasing already matched) ───────
    ('(روش|چطور|راه|طریقه|chetor)[^\n]{0,25}(خودکشی|خودکشی کنم|رگ زدن|suicide|self harm)',
     'self_harm', 'high', 'روش خودکشی — پاسخ باید به مسیر کمک هدایت شود'),

    -- ── malware, both word orders ─────────────────────────────────────────
    ('(ساخت|بساز|میساز|بنویس|مینویس|نوشتن|طراحی|sakht)[^\n]{0,25}(باج ?افزار|بدافزار|کیلاگر|ransomware|keylogger|malware)',
     'malware', 'high', 'ساخت بدافزار — نیت پیش از موضوع'),
    ('(باج ?افزار|بدافزار|کیلاگر|ransomware|keylogger|malware)[^\n]{0,25}(بساز|بنویس|مینویس|نوشتن|ساخت|طراحی)',
     'malware', 'high', 'ترتیب فارسی: «برام یه باج افزار بنویس»'),

    -- ── account takeover, both word orders ────────────────────────────────
    ('(هک|نفوذ|دزد|بدزد|سرقت|hack)[^\n]{0,25}(اینستاگرام|تلگرام|واتساپ|جیمیل|اکانت|instagram|telegram|whatsapp)',
     'account_takeover', 'high', 'هک حساب دیگران — نیت پیش از موضوع'),
    ('(اینستاگرام|تلگرام|واتساپ|جیمیل|instagram|telegram|whatsapp)[^\n]{0,25}(هک|نفوذ|بدزد|دزدی|سرقت|hack)',
     'account_takeover', 'high', 'ترتیب فارسی: «اینستاگرام یکی رو هک کنم»'),

    -- ── fraud / adult (unchanged) ─────────────────────────────────────────
    ('(شماره کارت|رمز دوم|cvv2?|فیشینگ|carding)[^\n]{0,25}(دزدی|سرقت|هک|جعل|فروش)',
     'fraud', 'high', 'کلاهبرداری بانکی'),
    ('(پورن|شهوانی|pornhub|xnxx|xvideos)',
     'sexual', 'medium', 'محتوای بزرگسال — فقط علامت‌گذاری، نه مسدودسازی')
ON CONFLICT (pattern) DO NOTHING;
