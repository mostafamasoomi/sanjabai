"""Admin API for the three free-tier limits.

Companion to ``services/free_tier_config.py`` (owns the cache and the
fail-safe defaults) and migration 0045 (seeds the three ``app_setting``
rows). Modelled on ``admin_watchdog.py`` / ``site_settings.py``: same
``admin_required`` auth, bare ``/admin/...`` prefix (the Next.js proxy
strips a leading ``/api`` so the panel calls ``/api/admin/free-tier-
settings``), ``_write_audit_log`` on every accepted write, Persian bodies.

Unlike the watchdog endpoint these values are NOT secrets -- they are three
integers an admin needs to see and set -- so ``GET`` returns them in full.

Read semantics: direct DB, no cache, no fail-open (returns 500 if the DB is
unreadable) so the panel never renders a guessed number as if it were the
stored one. The hot-path chat gate is the side that fails open, via
``free_tier_config.get_config``.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from database import async_session
from dependencies import admin_required, _write_audit_log
from services.free_tier_config import _DEFAULTS, _KEYS, _coerce_int, invalidate

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-field sane bounds. A limit of 0 is legal (it means "free tier fully
# closed"); the upper bounds stop a fat-fingered paste from seeding an
# effectively-infinite giveaway. The price ceiling is in Toman/M and today's
# most expensive served model is ~1.9M, so 100M is comfortably "no ceiling"
# without being unbounded.
_BOUNDS = {
    'free_hourly_limit': (0, 100000),
    'free_lifetime_limit': (0, 100000),
    'free_tier_max_input_per_million': (0, 100000000),
}

# Panel field name -> app_setting key. Both happen to be identical here, but
# the indirection matches admin_watchdog.py and keeps the wire contract
# explicit.
_FIELD_TO_KEY = {k: k for k in _KEYS}


@router.get('/admin/free-tier-settings')
async def get_free_tier_settings(request: Request) -> JSONResponse:
    """The three current values, in full, plus which are still at their
    default (row missing). Direct DB read, no cache, no fail-open."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT key AS setting_key, value FROM app_setting '
                    'WHERE key = ANY(:keys)'
                ),
                {'keys': list(_KEYS)},
            )
            rows = res.fetchall()
            db_values = {r.setting_key: r.value for r in rows}
    except Exception as e:
        logger.warning('GET /admin/free-tier-settings DB read failed: %s', e)
        return JSONResponse(
            {'detail': 'خطا در خواندن تنظیمات از پایگاه داده'}, status_code=500
        )

    values = {
        key: _coerce_int(db_values.get(key), _DEFAULTS[key]) for key in _KEYS
    }
    return JSONResponse({
        'values': values,
        'defaults': dict(_DEFAULTS),
        'rows_missing': [k for k in _KEYS if k not in db_values],
    })


@router.post('/admin/free-tier-settings')
async def update_free_tier_settings(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Write one or more limits. ``{"free_hourly_limit": 3, ...}``; each field
    optional, each a non-negative integer within its bound."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    if not isinstance(payload, dict) or not payload:
        return JSONResponse(
            {'detail': 'هیچ فیلدی برای بروزرسانی ارسال نشده است'}, status_code=400
        )

    unknown = set(payload) - set(_FIELD_TO_KEY)
    if unknown:
        return JSONResponse(
            {'detail': f'کلید ناشناخته: {", ".join(sorted(unknown))}'}, status_code=400
        )

    cleaned: dict[str, int] = {}
    for field, key in _FIELD_TO_KEY.items():
        if field not in payload:
            continue
        raw = payload[field]
        # Reject non-integers explicitly rather than coercing -- an admin who
        # types "3.5" or "abc" must see an error, not a silently floored value.
        if isinstance(raw, bool) or not isinstance(raw, int):
            if isinstance(raw, str) and raw.strip().lstrip('-').isdigit():
                raw = int(raw.strip())
            else:
                return JSONResponse(
                    {'detail': f'مقدار {field} باید یک عدد صحیح باشد'}, status_code=400
                )
        lo, hi = _BOUNDS[key]
        if raw < lo or raw > hi:
            return JSONResponse(
                {'detail': f'مقدار {field} باید بین {lo} و {hi} باشد'}, status_code=400
            )
        cleaned[key] = raw

    if not cleaned:
        return JSONResponse(
            {'detail': 'هیچ فیلدی برای بروزرسانی ارسال نشده است'}, status_code=400
        )

    try:
        async with async_session() as session:
            for key, value in cleaned.items():
                await session.execute(
                    sqlalchemy.text(
                        'INSERT INTO app_setting (key, value, updated_at) '
                        'VALUES (:k, :v, now()) '
                        'ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now()'
                    ),
                    {'k': key, 'v': json.dumps(value)},
                )
            await session.commit()
    except Exception as e:
        logger.warning('POST /admin/free-tier-settings DB write failed: %s', e)
        return JSONResponse(
            {'detail': 'خطا در ذخیرهٔ تنظیمات در پایگاه داده'}, status_code=500
        )

    invalidate()

    await _write_audit_log(
        'admin.free_tier_settings.update', target_type='free_tier_setting',
        target_id=','.join(sorted(cleaned)) if len(cleaned) > 1 else next(iter(cleaned)),
        details=dict(cleaned), request=request,
    )
    return JSONResponse({'status': 'ok', 'updated': cleaned})
