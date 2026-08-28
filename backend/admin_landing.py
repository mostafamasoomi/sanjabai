"""Admin write/delete API for landing page content overrides.

Companion to ``landing_content.py`` (owns ``ALLOWED_KEYS``, ``FROZEN_PATHS``,
``MAX_VALUE_BYTES``, ``frozen_conflicts()`` and ``invalidate_cache()`` -- all
imported from there rather than duplicated) and migration
``0052_landing_content.sql``. Auth and response shape follow
``admin_free_tier.py``: same ``admin_required``, bare ``/admin/...`` prefix
(the Next.js proxy strips a leading ``/api``), ``_write_audit_log`` on every
accepted write, Persian-first bilingual error bodies via ``i18n.err``.

Read semantics (``GET``): direct DB, no cache, same reasoning as
``admin_free_tier.py`` -- the panel must never render a guessed value as if
it were the stored one. It also returns ``allowed_keys`` and
``frozen_paths`` so the panel knows, without hardcoding a second copy of
either list, which keys exist at all and which JSON paths inside them it
must render read-only. The public, cached, fail-open GET
``/landing/content`` lives in ``landing_content.py`` -- this module never
answers that route.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session
from dependencies import admin_required, _write_audit_log
from i18n import err
from landing_content import (
    ALLOWED_KEYS,
    FROZEN_PATHS,
    MAX_VALUE_BYTES,
    frozen_conflicts,
    invalidate_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/admin/landing/content')
async def get_admin_landing_content(request: Request) -> JSONResponse:
    """Every stored override in full, plus the allowed-keys and
    frozen-paths metadata a panel needs to know what it may edit at all."""
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'The database is unavailable.', 500)

    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                'SELECT key, value, updated_at, updated_by FROM landing_content '
                'ORDER BY key'
            ))
            rows = res.fetchall()
    except Exception as e:
        logger.warning('GET /admin/landing/content DB read failed: %s', e)
        return err(
            'خطا در خواندن محتوای لندینگ از پایگاه داده',
            'Failed to read landing content from the database.', 500,
        )

    overrides: dict[str, Any] = {}
    for row in rows:
        m = row._mapping
        overrides[m['key']] = {
            'value': m['value'],
            'updatedAt': m['updated_at'],
            'updatedBy': m['updated_by'],
        }

    return JSONResponse(jsonable_encoder({
        'overrides': overrides,
        'allowedKeys': sorted(ALLOWED_KEYS),
        'frozenPaths': {k: list(v) for k, v in FROZEN_PATHS.items()},
    }))


@router.put('/admin/landing/content/{key}')
async def put_landing_content(key: str, request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Upsert one module's override. Body: `{"value": <json>}`.

    Rejects (in order): an unrecognised key, a missing/non-serialisable
    `value`, a value over `MAX_VALUE_BYTES`, and a value that would fill in
    one of that key's frozen (live-counted-claim) paths. Only after all
    four pass does it touch the database.
    """
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)

    if key not in ALLOWED_KEYS:
        return err(
            f'کلید نامعتبر: {key}',
            f'Invalid key: {key}.', 400,
        )

    if not isinstance(payload, dict) or 'value' not in payload:
        return err(
            'بدنه‌ی درخواست باید شامل فیلد value باشد',
            'The request body must include a "value" field.', 400,
        )

    value = payload['value']

    try:
        raw = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return err(
            'مقدار ارسالی قابل تبدیل به JSON نیست',
            'The submitted value is not JSON-serialisable.', 400,
        )

    if len(raw.encode('utf-8')) > MAX_VALUE_BYTES:
        return err(
            f'حجم محتوا نباید بیشتر از {MAX_VALUE_BYTES // 1024} کیلوبایت باشد',
            f'Content size must not exceed {MAX_VALUE_BYTES // 1024} KB.', 413,
        )

    conflicts = frozen_conflicts(key, value)
    if conflicts:
        return err(
            'این فیلدها به‌صورت زنده محاسبه می‌شوند و از پنل ادمین قابل ویرایش '
            'نیستند: ' + '، '.join(conflicts),
            'These fields are computed live and cannot be edited from the '
            'admin panel: ' + ', '.join(conflicts), 400,
        )

    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'The database is unavailable.', 500)

    try:
        async with async_session() as session:
            # updated_by stays NULL -- this backend's admin auth has no
            # per-admin-user id to attribute the write to (see migration
            # 0052's rationale).
            await session.execute(
                sqlalchemy.text(
                    'INSERT INTO landing_content (key, value, updated_at, updated_by) '
                    'VALUES (:k, :v, now(), NULL) '
                    'ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), '
                    'updated_by = NULL'
                ),
                {'k': key, 'v': raw},
            )
            await session.commit()
    except Exception as e:
        logger.warning('PUT /admin/landing/content/%s DB write failed: %s', key, e)
        return err(
            'خطا در ذخیره‌ی محتوای لندینگ',
            'Failed to save the landing content.', 500,
        )

    await invalidate_cache()

    await _write_audit_log(
        'admin.landing_content.update', target_type='landing_content',
        target_id=key, details={'key': key}, request=request,
    )
    return JSONResponse({'status': 'ok', 'key': key, 'value': value})


@router.delete('/admin/landing/content/{key}')
async def delete_landing_content(key: str, request: Request) -> JSONResponse:
    """Remove one module's override, reverting it to the static frontend
    default. Deleting a key with no stored override is a harmless no-op."""
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)

    if key not in ALLOWED_KEYS:
        return err(
            f'کلید نامعتبر: {key}',
            f'Invalid key: {key}.', 400,
        )

    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'The database is unavailable.', 500)

    try:
        async with async_session() as session:
            await session.execute(
                sqlalchemy.text('DELETE FROM landing_content WHERE key = :k'),
                {'k': key},
            )
            await session.commit()
    except Exception as e:
        logger.warning('DELETE /admin/landing/content/%s DB write failed: %s', key, e)
        return err(
            'خطا در حذف محتوای لندینگ',
            'Failed to delete the landing content.', 500,
        )

    await invalidate_cache()

    await _write_audit_log(
        'admin.landing_content.delete', target_type='landing_content',
        target_id=key, details=None, request=request,
    )
    return JSONResponse({'status': 'ok', 'key': key, 'deleted': True})
