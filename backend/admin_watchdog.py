"""Admin API for the Telegram alerting credentials.

Companion to ``services/watchdog_settings.py`` (read that module's
docstring first -- it owns the precedence rules and the fail-open
contract) and to migration 0044, which seeds the two ``app_setting`` rows.

Modelled line for line on ``site_settings.py``: same ``admin_required``
auth, same bare ``/admin/...`` route prefix (the Next.js proxy strips a
leading ``/api`` before forwarding, so the panel calls
``/api/admin/watchdog-settings``), same ``_write_audit_log`` on every
accepted write, same Persian error bodies.

── The one thing this router does differently, and why ────────────────────
It NEVER returns the bot token. ``GET`` answers with
``bot_token_set`` plus ``bot_token_hint`` -- the last 4 characters -- and
nothing else, mirroring how ``api_keys.py`` shows a stored key as
``prefix + bullets`` and only ever hands out the full secret at the moment
it is minted. A settings form that round-trips the real credential to the
browser turns every admin session, every proxy log and every screenshot
into a place the bot token can leak from, for the sole benefit of letting
an admin re-read something they already had to know in order to type it.
So the field is write-only from the panel's point of view; saving replaces
it, and saving an empty string clears it back to the environment fallback.

``chat_id`` IS returned in full. It is an addressing label, not a
credential -- possessing it grants nothing without the token -- and an
admin who cannot see which chat the alerts go to cannot verify the setting
is right, which is the whole reason this page exists.

── Read semantics -- direct DB, no cache, no fail-open ────────────────────
Same split as ``site_settings.py``. The hot-path helper fails open to the
environment because alerting config must never break chat; this endpoint
does the opposite and returns 500, because a panel that renders "not
configured" when the truth is unknown is a lie the owner could act on --
they would go set a credential that is already set, or believe alerting is
dead when it is live.
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
from services.watchdog_settings import (
    ENV_BOT_TOKEN,
    ENV_CHAT_ID,
    KEY_BOT_TOKEN,
    KEY_CHAT_ID,
    SETTING_KEYS,
    _coerce,
    _env,
    _resolve,
    invalidate_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Telegram bot tokens are ~46 characters; a chat id is short. 512 is far
# above anything legitimate and far below anything that could bloat the
# app_setting row, and rejecting past it keeps a paste accident (a whole
# .env file into the field) from becoming a stored credential.
_MAX_VALUE_CHARS = 512

_HINT_CHARS = 4


def _hint(value: str) -> str:
    """Last 4 characters, and only when there are enough characters that
    revealing them is not revealing the value. A 5-character secret whose
    last 4 are shown is a 1-character secret."""
    if len(value) <= _HINT_CHARS * 2:
        return ''
    return value[-_HINT_CHARS:]


@router.get('/admin/watchdog-settings')
async def get_watchdog_settings(request: Request) -> JSONResponse:
    """Masked view of both credentials, plus where each one comes from.

    Reads the database directly -- no cache, no fail-open -- see the module
    docstring. The environment fallback is folded in here rather than
    reported separately, because "is alerting on" is the question the admin
    actually has and the answer depends on both sources.
    """
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
                {'keys': list(SETTING_KEYS)},
            )
            rows = res.fetchall()
            db_values = {r.setting_key: r.value for r in rows}
    except Exception as e:
        logger.warning('GET /admin/watchdog-settings DB read failed: %s', e)
        return JSONResponse(
            {'detail': 'خطا در خواندن تنظیمات از پایگاه داده'}, status_code=500
        )

    db_token = _coerce(db_values.get(KEY_BOT_TOKEN), KEY_BOT_TOKEN)
    db_chat = _coerce(db_values.get(KEY_CHAT_ID), KEY_CHAT_ID)
    token, token_source = _resolve(db_token, _env(ENV_BOT_TOKEN))
    chat, chat_source = _resolve(db_chat, _env(ENV_CHAT_ID))

    return JSONResponse({
        # Never the token itself. See the module docstring.
        'bot_token_set': bool(token),
        'bot_token_hint': _hint(token),
        'bot_token_source': token_source,
        # An addressing label, not a credential -- returned in full so the
        # admin can actually verify it.
        'chat_id': chat,
        'chat_id_set': bool(chat),
        'chat_id_source': chat_source,
        # Both halves required; either one missing means nothing is sent.
        'active': bool(token and chat),
        'env_available': {
            'bot_token': bool(_env(ENV_BOT_TOKEN)),
            'chat_id': bool(_env(ENV_CHAT_ID)),
        },
        'rows_missing': [k for k in SETTING_KEYS if k not in db_values],
    })


@router.post('/admin/watchdog-settings')
async def update_watchdog_settings(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Write either or both credentials. ``{"bot_token": "...",
    "chat_id": "..."}``; both fields optional, an empty string clears that
    credential back to the environment fallback.

    Audit-logged like every other admin mutation -- but the entry records
    only whether each field was SET or CLEARED, never the value. An audit
    trail that copies the secret into a second table has not protected
    anything, it has duplicated the exposure.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    if not isinstance(payload, dict) or not payload:
        return JSONResponse(
            {'detail': 'هیچ فیلدی برای بروزرسانی ارسال نشده است'}, status_code=400
        )

    field_to_key = {'bot_token': KEY_BOT_TOKEN, 'chat_id': KEY_CHAT_ID}
    unknown = set(payload) - set(field_to_key)
    if unknown:
        return JSONResponse(
            {'detail': f'کلید ناشناخته: {", ".join(sorted(unknown))}'}, status_code=400
        )

    cleaned: dict[str, str] = {}
    for field, key in field_to_key.items():
        if field not in payload:
            continue
        value = payload[field]
        if value is None:
            value = ''
        if not isinstance(value, str):
            return JSONResponse(
                {'detail': f'مقدار {field} باید رشته باشد'}, status_code=400
            )
        value = value.strip()
        if len(value) > _MAX_VALUE_CHARS:
            return JSONResponse(
                {'detail': f'مقدار {field} بیش از حد طولانی است'}, status_code=400
            )
        # A newline inside a credential is always a paste accident and
        # would be sent verbatim into a Telegram URL.
        if any(c in value for c in '\n\r\t'):
            return JSONResponse(
                {'detail': f'مقدار {field} نباید شامل خط جدید یا تب باشد'}, status_code=400
            )
        cleaned[key] = value

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
        logger.warning('POST /admin/watchdog-settings DB write failed: %s', e)
        return JSONResponse(
            {'detail': 'خطا در ذخیرهٔ تنظیمات در پایگاه داده'}, status_code=500
        )

    await invalidate_cache()

    # Values deliberately absent -- only the ACTION per field.
    details = {k: ('set' if v else 'cleared') for k, v in cleaned.items()}
    await _write_audit_log(
        'admin.watchdog_settings.update', target_type='watchdog_setting',
        target_id=','.join(sorted(cleaned)) if len(cleaned) > 1 else next(iter(cleaned)),
        details=details, request=request,
    )
    return JSONResponse({'status': 'ok', 'updated': details})
