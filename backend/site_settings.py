"""Runtime, admin-editable site-control switches.

Closes a real gap in the admin panel: today there is no way for an admin to
turn a section of the site off without an SSH session and a container
restart (every existing kill switch -- ``TASK_SCHEDULER_ENABLED``,
``OPENROUTER_ENABLED`` -- is an environment variable). This module is the
store and the API for a small set of boolean flags an admin can flip from
the panel; it does NOT wire those flags into chat/images/signup/etc, and it
does not touch the env-var switches it mirrors -- see the module-level
``FLAGS`` registry below and the migration
(``migrations/0036_site_settings.sql``) for exactly what is and is not live
yet.

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
    description_fa: str
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
        description_fa='کل سایت را برای کاربران عادی غیرفعال می‌کند (ادمین همچنان دسترسی دارد).',
        default=False,
        wired=False,
        wire_note='هنوز به هیچ‌جا وصل نشده -- باید در میان‌افزار یا صفحات کاربر بررسی شود.',
    ),
    'signups_enabled': FlagMeta(
        key='signups_enabled',
        label_fa='ثبت‌نام کاربر جدید',
        description_fa='امکان ساخت حساب کاربری جدید را باز/بسته می‌کند.',
        default=True,
        wired=False,
        wire_note='باید در backend/auth.py، ابتدای تابع signup() بررسی شود.',
    ),
    'chat_enabled': FlagMeta(
        key='chat_enabled',
        label_fa='گفتگو (چت)',
        description_fa='مسیر اصلی گفتگو با مدل‌ها را برای همهٔ کاربران باز/بسته می‌کند.',
        default=True,
        wired=False,
        wire_note='باید در backend/chat.py، ابتدای هندلر /v1/chat/completions بررسی شود.',
    ),
    'image_generation_enabled': FlagMeta(
        key='image_generation_enabled',
        label_fa='تولید تصویر',
        description_fa='مسیر تولید تصویر را برای همهٔ کاربران باز/بسته می‌کند (مستقل از در دسترس بودن هر مدل).',
        default=True,
        wired=False,
        wire_note='باید در backend/images.py، ابتدای هندلر /v1/images/generations بررسی شود.',
    ),
    'task_scheduler_enabled': FlagMeta(
        key='task_scheduler_enabled',
        label_fa='زمان‌بند وظایف (Task Scheduler)',
        description_fa=(
            'اجرای حلقهٔ پس‌زمینهٔ وظایف زمان‌بندی‌شده را کنترل می‌کند. هم‌اکنون این مقدار '
            'فقط در پایگاه داده ذخیره می‌شود -- رفتار واقعی همچنان از متغیر محیطی '
            'TASK_SCHEDULER_ENABLED می‌آید.'
        ),
        default=False,
        wired=False,
        wire_note=(
            'مقدار زندهٔ فعلی از env var می‌آید (services/task_scheduler.py:60، '
            'TASK_SCHEDULER_ENABLED). این کلید فقط داده را نگه می‌دارد، تا وصل شدن '
            'واقعی در یک تغییر جداگانه.'
        ),
    ),
    'openrouter_enabled': FlagMeta(
        key='openrouter_enabled',
        label_fa='OpenRouter (تأمین‌کننده)',
        description_fa=(
            'مسیر تأمین OpenRouter را کنترل می‌کند. هم‌اکنون این مقدار فقط در پایگاه داده '
            'ذخیره می‌شود -- رفتار واقعی همچنان از متغیر محیطی OPENROUTER_ENABLED می‌آید.'
        ),
        default=False,
        wired=False,
        wire_note='مقدار زندهٔ فعلی از env var می‌آید (backend/providers.py:139).',
    ),
}


def _cache_key(flag_key: str) -> str:
    return f'{_CACHE_PREFIX}{flag_key}'


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
            return bool(json.loads(cached))
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
            value = meta.default if row is None or row.value is None else bool(row.value)
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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

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
        return JSONResponse({'detail': 'خطا در خواندن تنظیمات از پایگاه داده'}, status_code=500)

    flags = []
    for meta in FLAGS.values():
        raw = db_values.get(meta.key)
        value = meta.default if raw is None else bool(raw)
        flags.append({
            'key': meta.key,
            'value': value,
            'default': meta.default,
            'label_fa': meta.label_fa,
            'description_fa': meta.description_fa,
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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    if not isinstance(payload, dict) or not payload:
        return JSONResponse({'detail': 'هیچ فیلدی برای بروزرسانی ارسال نشده است'}, status_code=400)

    unknown = set(payload) - set(FLAGS)
    if unknown:
        return JSONResponse({'detail': f'کلید ناشناخته: {", ".join(sorted(unknown))}'}, status_code=400)

    cleaned: dict[str, bool] = {}
    for k, v in payload.items():
        if not isinstance(v, bool):
            return JSONResponse(
                {'detail': f'مقدار {k} باید true/false باشد'}, status_code=400
            )
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
