"""Runtime, admin-editable site-control switches.

Closes a real gap in the admin panel: today there is no way for an admin to
turn a section of the site off without an SSH session and a container
restart (every existing kill switch -- ``TASK_SCHEDULER_ENABLED``,
``OPENROUTER_ENABLED`` -- is an environment variable). This module is the
store and the API for a small set of boolean flags an admin can flip from
the panel.

All six flags are now wired to real behaviour; the per-flag ``wire_note``
in the ``FLAGS`` registry below says exactly where each one is read, and
the admin panel renders that note. Keep those notes true: a flag whose
``wired`` bit says ``True`` while nothing reads it is precisely the "button
that confirms success and does nothing" failure this whole section exists
to remove.

The two env-var switches this store mirrors (``TASK_SCHEDULER_ENABLED``,
``OPENROUTER_ENABLED``) are ORed with their DB flag rather than replaced --
either source saying "on" is on. That way turning a flag on from the panel
never requires an SSH session, and nothing that works today via the
environment stops working.

── Storage: app_setting, not a new table ───────────────────────────────────
``app_setting`` (``key TEXT PRIMARY KEY, value JSONB NOT NULL, updated_at``)
already exists and already holds ``global_markup_pct`` -- a generic
key/value settings store, not something markup-specific. This project
already carries two admin UIs writing ``credit_packages`` as recorded
technical debt; a second settings table next to one that already does the
job would repeat that mistake. So every flag below is just another row in
``app_setting``, seeded by migration 0036.

── Fail-open contract -- READ THIS before adding a call site ───────────────
:func:`get_site_flag` is what a *feature* call site (chat.py, images.py,
auth.py, ...) should call to check a flag. On any Redis or DB error it
returns the flag's registered ``default`` -- which migration 0036 chose to
be exactly today's production behaviour -- rather than raising or guessing
some other value. A settings-store hiccup must never take the site down;
see backend/services/free_tier.py's ``has_paid``/``has_balance`` for the
same fail-open idiom applied to a different gate. This is DIFFERENT from
the admin GET endpoint below, which reads the database directly (no cache,
no fail-open) and returns 500 on a real error -- an admin control panel
must never render a switch as "off" when the truth is unknown, because the
owner could act on that lie.

── Route prefix ─────────────────────────────────────────────────────────
Registered as bare ``/admin/site-settings`` (no leading ``/api``), matching
every other admin router in this codebase (``admin_packages.py``,
``admin_catalog.py``). The Next.js proxy strips a leading ``/api`` before
forwarding, so the frontend calls ``/api/admin/site-settings`` and this
route is what it reaches. ``tests/test_api_prefix_routes.py`` only requires
a bare twin for routes registered *as* ``/api/...``, which this module
never does.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from database import async_session, rds
from dependencies import admin_required, _write_audit_log
from i18n import err

logger = logging.getLogger(__name__)

router = APIRouter()

# Short TTL per the orchestrator's brief -- a flag flip should reach every
# process within seconds, not the ~10 minutes the catalog cache tolerates.
# Every write below also deletes the affected key's cache entry immediately
# (same belt-and-suspenders pattern as admin_catalog.py's markup writes), so
# this TTL is only what a *concurrent* reader waits out in the worst case.
_CACHE_TTL_SECONDS = 30
_CACHE_PREFIX = 'cache:site_settings:'


@dataclass(frozen=True)
class FlagMeta:
    """One admin-editable switch. ``default`` is also the fail-open value
    (see module docstring) -- both because that is what migration 0036
    seeded (today's real behaviour) and because a value that is safe to
    fall back to on error is, by construction, not a restrictive one."""

    key: str
    label_fa: str
    label_en: str
    description_fa: str
    description_en: str
    default: bool
    wired: bool
    wire_note: str  # human-readable pointer to the call site(s), for the panel


# The full set of flags this store knows about. Adding a new one here is
# just a Python change; giving it a database row still requires a new
# migration (0037+) that seeds its default -- this registry is metadata,
# not the source of truth for what exists in app_setting.
FLAGS: dict[str, FlagMeta] = {
    'maintenance_mode': FlagMeta(
        key='maintenance_mode',
        label_fa='حالت تعمیر و نگهداری',
        label_en='Maintenance mode',
        description_fa=(
            'همهٔ درخواست‌های کاربر عادی به API را با خطای ۵۰۳ رد می‌کند؛ ادمین همچنان '
            'دسترسی کامل دارد. مسیرهای /health و /admin و ورود و /status باز می‌مانند تا '
            'سایت در همان حالت هم قابل بازیابی و پایش باشد.'
        ),
        description_en=(
            'Rejects every regular-user request to the API with a 503 error; the admin '
            'still has full access. The /health, /admin, login and /status routes stay '
            'open so the site remains recoverable and observable even in this state.'
        ),
        default=False,
        wired=True,
        wire_note=(
            'وصل است: middleware/maintenance.py، ثبت‌شده در app.py به‌عنوان داخلی‌ترین لایه. '
            'توجه: صفحات Next.js همچنان رندر می‌شوند ولی داده‌شان ۵۰۳ می‌گیرد -- یعنی کاربر '
            'صفحهٔ خطادار می‌بیند، نه یک صفحهٔ «در حال تعمیر» اختصاصی.'
        ),
    ),
    'signups_enabled': FlagMeta(
        key='signups_enabled',
        label_fa='ثبت‌نام کاربر جدید',
        label_en='New user signups',
        description_fa='امکان ساخت حساب کاربری جدید را باز/بسته می‌کند.',
        description_en='Turns the ability to create a new user account on/off.',
        default=True,
        wired=True,
        wire_note='وصل است: backend/auth.py، اولین دستور signup() -- قبل از چک کپچا، پس کپچا مصرف نمی‌شود. خاموش = ۴۰۳.',
    ),
    'chat_enabled': FlagMeta(
        key='chat_enabled',
        label_fa='گفتگو (چت)',
        label_en='Chat',
        description_fa='مسیر اصلی گفتگو با مدل‌ها را برای همهٔ کاربران باز/بسته می‌کند.',
        description_en='Turns the main chat-with-models route on/off for all users.',
        default=True,
        wired=True,
        wire_note=(
            'وصل است: هر چهار مسیر گفتگو -- /v1/chat/completions، /v1/chat/with-file، '
            '/v1/smart-chat و /v1/compare -- از راه chat._chat_disabled_response(). '
            'گیت بعد از چک ۴۰۱ و قبل از هر رزرو کیف پول است، پس خاموش‌بودن هیچ پولی بلوکه نمی‌کند. خاموش = ۵۰۳.'
        ),
    ),
    'image_generation_enabled': FlagMeta(
        key='image_generation_enabled',
        label_fa='تولید تصویر',
        label_en='Image generation',
        description_fa='مسیر تولید تصویر را برای همهٔ کاربران باز/بسته می‌کند (مستقل از در دسترس بودن هر مدل).',
        description_en=(
            'Turns the image-generation route on/off for all users '
            '(independent of any individual model\'s availability).'
        ),
        default=True,
        wired=True,
        wire_note='وصل است: backend/images.py، ابتدای /v1/images/generations، قبل از رزرو. خاموش = ۵۰۳.',
    ),
    'task_scheduler_enabled': FlagMeta(
        key='task_scheduler_enabled',
        label_fa='زمان‌بند وظایف (Task Scheduler)',
        label_en='Task scheduler',
        description_fa=(
            'اجرای حلقهٔ پس‌زمینهٔ وظایف زمان‌بندی‌شده را کنترل می‌کند. روشن‌کردن این کلید '
            'زمان‌بند را بدون ری‌استارت کانتینر فعال می‌کند (حداکثر تا یک تیک، ۶۰ ثانیه).'
        ),
        description_en=(
            'Controls whether the scheduled-task background loop runs. Turning this flag '
            'on enables the scheduler without a container restart (within one tick, up to '
            '60 seconds).'
        ),
        default=False,
        wired=True,
        wire_note=(
            'وصل است: services/task_scheduler.py، به‌صورت «env var یا فلگ DB» -- یعنی '
            'روشن‌بودن هرکدام کافی است و متغیر محیطی TASK_SCHEDULER_ENABLED هرگز نادیده '
            'گرفته نمی‌شود. حلقه در هر تیک دوباره فلگ را می‌خواند، پس تغییر شما حداکثر '
            'تا ۶۰ ثانیه اثر می‌کند. تا وقتی خاموش است هیچ تسکی claim یا اجرا نمی‌شود.'
        ),
    ),
    'logical_routing_enabled': FlagMeta(
        key='logical_routing_enabled',
        label_fa='مسیریابی مدل منطقی',
        label_en='Logical model routing',
        description_fa=(
            'اجازه می‌دهد یک کلید مدل منطقی (مثل claude-sonnet-5) به بهترین ردیف زندهٔ '
            'کاتالوگ resolve شود. خاموش = رفتار امروز، بایت‌به‌بایت. روشن = فقط مدل‌هایی که '
            'در کاتالوگ هیچ تطبیقی ندارند از لایهٔ منطقی عبور می‌کنند؛ هیچ مدل موجودی مسیرش عوض نمی‌شود.'
        ),
        description_en=(
            'Allows a logical model key (e.g. claude-sonnet-5) to resolve to the best live '
            'catalog row. Off = today\'s behavior, byte for byte. On = only model keys with '
            'no match at all in the catalog pass through the logical layer; no existing '
            'model\'s routing changes.'
        ),
        default=False,
        wired=True,
        wire_note=(
            'وصل است: chat_models.py، انتهای _resolve_public_model() -- یعنی همان نقطهٔ واحدی '
            'که هر مسیر چت/مقایسه/اسمارت‌چت قبل از گیت رایگان، رزرو کیف پول و صورتحساب از آن '
            'رد می‌شود. لایهٔ منطقی فقط وقتی امتحان می‌شود که رشتهٔ ورودی در کاتالوگ هیچ '
            'تطبیقی نداشته باشد، پس روشن‌کردن این کلید مسیر هیچ مدلی را که امروز کار می‌کند '
            'عوض نمی‌کند. services/model_resolver.py هرگز raise نمی‌کند و None آن یعنی '
            '«همان رفتار قبلی» -- پس بدترین حالت روشن‌بودن، همان رفتار خاموش است.'
        ),
    ),
    'openrouter_enabled': FlagMeta(
        key='openrouter_enabled',
        label_fa='OpenRouter (تأمین‌کننده)',
        label_en='OpenRouter (provider)',
        description_fa=(
            'مسیر تأمین OpenRouter را کنترل می‌کند. ⚠️ روشن‌کردن این کلید به‌تنهایی کافی '
            'نیست -- کلید OPENROUTER_API_KEY هم باید ست باشد، وگرنه پروایدر بی‌صدا نادیده '
            'گرفته می‌شود.'
        ),
        description_en=(
            'Controls the OpenRouter supply route. ⚠️ Turning this flag on alone '
            'is not enough -- the OPENROUTER_API_KEY must also be set, or the provider is '
            'silently ignored.'
        ),
        default=False,
        wired=True,
        wire_note=(
            'وصل است: backend/providers.py، به‌صورت «env var یا فلگ DB»؛ شرط داشتن کلید API '
            'دست‌نخورده باقی مانده. چون configured_providers() همگام است، خواندن فلگ از یک '
            'کش کوتاه (۵ ثانیه) با تازه‌سازی پس‌زمینه می‌آید -- پس تغییر شما با چند ثانیه '
            'تأخیر اثر می‌کند، نه فوری.'
        ),
    ),
}


def _cache_key(flag_key: str) -> str:
    return f'{_CACHE_PREFIX}{flag_key}'


def _coerce_flag(raw: Any, meta: FlagMeta, source: str) -> bool:
    """A stored value becomes a flag only if it is genuinely a boolean.

    Every write path in this module stores ``json.dumps(bool)``, and the
    live database was checked directly: all six rows come back from asyncpg
    as real Python ``bool``. So a value that is anything else is corrupt or
    hand-edited, not a flag, and it falls back to the registered default.

    This is deliberately stricter than the ``bool(raw)`` it replaces, which
    was wrong in the one direction that matters most. ``bool()`` maps the
    STRING ``'false'`` to ``True`` and the integer ``1`` to ``True`` -- so a
    single mistyped row (``'false'`` instead of ``false``) would have read
    as "maintenance mode ON" and taken the whole site down, with the panel
    showing the same wrong answer back to the admin. Falling back to the
    default instead means a malformed value can only ever produce today's
    known-good behaviour, never a surprise site-wide switch.
    """
    if isinstance(raw, bool):
        return raw
    logger.warning(
        'site_settings: %s value for %r is %r (%s), not a boolean -- '
        'falling back to the registered default %r; this row needs fixing',
        source, meta.key, raw, type(raw).__name__, meta.default,
    )
    return meta.default


async def get_site_flag(key: str) -> bool:
    """The read helper other backend modules should call to check a flag.

    Fails open to ``FLAGS[key].default`` on any Redis/DB error, an unknown
    key, or when the row does not exist yet -- see the module docstring for
    why. Never raises.
    """
    meta = FLAGS.get(key)
    if meta is None:
        logger.warning('get_site_flag: unknown flag %r, failing open to False', key)
        return False

    try:
        cached = await rds.get(_cache_key(key))
        if cached is not None:
            return _coerce_flag(json.loads(cached), meta, 'cached')
    except Exception as e:
        logger.warning('site_settings cache read failed for %s: %s', key, e)

    try:
        if async_session is None:
            return meta.default
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text('SELECT value FROM app_setting WHERE key = :k'), {'k': key}
            )
            row = res.fetchone()
            value = (
                meta.default if row is None or row.value is None
                else _coerce_flag(row.value, meta, 'database')
            )
    except Exception as e:
        logger.warning('site_settings DB read failed for %s: %s', key, e)
        return meta.default

    try:
        await rds.setex(_cache_key(key), _CACHE_TTL_SECONDS, json.dumps(value))
    except Exception as e:
        logger.warning('site_settings cache write failed for %s: %s', key, e)

    return value


@router.get('/admin/site-settings')
async def get_site_settings(request: Request) -> JSONResponse:
    """Every known flag with its live DB value and panel metadata.

    Reads the database directly -- no cache, no fail-open -- because this
    is the admin's ground truth, not a hot-path gate. On a real DB error
    this returns 500 rather than a fabricated "all off" payload: a switch
    shown as off when the truth is unknown is a lie the owner could act on.
    """
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    try:
        async with async_session() as session:
            # Column aliased to `flag_key` (not `key`) out of caution --
            # SQLAlchemy Row objects are not guaranteed to leave a
            # column literally named `key` accessible as a clean attribute
            # rather than shadowing something on the Row class itself.
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT key AS flag_key, value FROM app_setting WHERE key = ANY(:keys)'
                ),
                {'keys': list(FLAGS.keys())},
            )
            db_values = {r.flag_key: r.value for r in res.fetchall()}
    except Exception as e:
        logger.warning('GET /admin/site-settings DB read failed: %s', e)
        return err('خطا در خواندن تنظیمات از پایگاه داده', 'Failed to read settings from the database.', 500)

    flags = []
    for meta in FLAGS.values():
        raw = db_values.get(meta.key)
        value = meta.default if raw is None else _coerce_flag(raw, meta, 'database')
        flags.append({
            'key': meta.key,
            'value': value,
            'default': meta.default,
            'label_fa': meta.label_fa,
            'label_en': meta.label_en,
            'description_fa': meta.description_fa,
            'description_en': meta.description_en,
            'wired': meta.wired,
            'wire_note': meta.wire_note,
            'row_missing': meta.key not in db_values,
        })
    return JSONResponse({'flags': flags})


@router.post('/admin/site-settings')
async def update_site_settings(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Update one or more flags. Payload is ``{flag_key: bool, ...}``.

    Every accepted write is audit-logged (one entry per request, listing
    every key/value actually changed) -- flipping a site-wide switch must
    be traceable to who did it, same as every other admin mutation in this
    codebase (see admin_packages.py / admin_catalog.py).
    """
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    if not isinstance(payload, dict) or not payload:
        return err('هیچ فیلدی برای بروزرسانی ارسال نشده است', 'No fields were submitted to update.', 400)

    unknown = set(payload) - set(FLAGS)
    if unknown:
        return err(
            f'کلید ناشناخته: {", ".join(sorted(unknown))}',
            f'Unknown key(s): {", ".join(sorted(unknown))}', 400,
        )

    cleaned: dict[str, bool] = {}
    for k, v in payload.items():
        if not isinstance(v, bool):
            return err(f'مقدار {k} باید true/false باشد', f'Value of {k} must be true/false.', 400)
        cleaned[k] = v

    async with async_session() as session:
        for k, v in cleaned.items():
            await session.execute(
                sqlalchemy.text(
                    "INSERT INTO app_setting (key, value, updated_at) "
                    "VALUES (:k, :v, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now()"
                ),
                {'k': k, 'v': json.dumps(v)},
            )
        await session.commit()

    try:
        await rds.delete(*[_cache_key(k) for k in cleaned])
    except Exception as e:
        logger.warning('site_settings cache invalidation failed: %s', e)

    await _write_audit_log(
        'admin.site_settings.update', target_type='site_setting',
        target_id=','.join(sorted(cleaned)) if len(cleaned) > 1 else next(iter(cleaned)),
        details=cleaned, request=request,
    )
    return JSONResponse({'status': 'ok', 'updated': cleaned})
