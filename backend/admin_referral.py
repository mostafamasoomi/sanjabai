"""Admin API for the referral reward: the three admin-tunable numbers plus
an at-a-glance count of what has actually happened.

Companion to ``services/referral.py`` (owns the cache, the fail-safe
defaults, and the settlement logic) and migration 0051 (creates
``referral_reward`` and seeds the three ``app_setting`` rows, all at zero).
Modelled on ``admin_free_tier.py``: same ``admin_required`` auth, bare
``/admin/...`` prefix (the Next.js proxy strips a leading ``/api``, so the
panel calls ``/api/admin/referral/settings``), ``_write_audit_log`` on
every accepted write, Persian bodies, ``invalidate()`` after a successful
write so the payment-callback path picks up a change immediately instead
of waiting out the 60s cache.

These values are NOT secrets -- three integers plus some counts an admin
needs to see and set -- so ``GET`` returns them in full, direct-DB, no
cache, no fail-open (a 500 here means the panel honestly can't read the
setting, rather than rendering a guessed number as if it were the stored
one). The hot-path settlement call is the side that fails open, via
``services.referral.config()``.
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
from i18n import err
from services.referral import _DEFAULTS, _KEYS, _coerce_int, invalidate

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-field sane bounds. A limit of 0 is legal (it means "referral reward
# off", which is also today's seeded state). The upper bound on either
# money field stops a fat-fingered paste from seeding a giveaway well
# beyond what any real credit-package purchase looks like on this catalog.
_BOUNDS = {
    'referral_reward_toman': (0, 500000),
    'referral_invitee_reward_toman': (0, 500000),
    'referral_reward_cap': (0, 100000),
}

# Panel field name -> app_setting key. Identical here (matches
# admin_free_tier.py's indirection, kept for the same reason: the wire
# contract stays explicit even though the mapping is trivial today).
_FIELD_TO_KEY = {k: k for k in _KEYS}

_COUNTS_SQL = sqlalchemy.text(
    "SELECT "
    "count(*) AS total, "
    "count(*) FILTER (WHERE status = 'pending') AS pending, "
    "count(*) FILTER (WHERE status = 'paid') AS paid, "
    "count(*) FILTER (WHERE status = 'capped') AS capped, "
    "COALESCE(SUM(inviter_amount_toman + invitee_amount_toman) "
    "  FILTER (WHERE status = 'paid'), 0) AS total_paid_toman "
    "FROM referral_reward"
)


@router.get('/admin/referral/settings')
async def get_referral_settings(request: Request) -> JSONResponse:
    """The three current values, in full, plus overall referral_reward
    counts (pending/paid/capped and the total actually paid out). Direct DB
    read, no cache, no fail-open."""
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'The database is unavailable.', 500)

    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT key AS setting_key, value FROM app_setting '
                    'WHERE key = ANY(:keys)'
                ),
                {'keys': list(_KEYS)},
            )
            db_values = {r.setting_key: r.value for r in res.fetchall()}

            counts_res = await session.execute(_COUNTS_SQL)
            counts_row = counts_res.fetchone()
    except Exception as e:
        logger.warning('GET /admin/referral/settings DB read failed: %s', e)
        return err(
            'خطا در خواندن تنظیمات از پایگاه داده',
            'Failed to read settings from the database.', 500,
        )

    values = {
        key: _coerce_int(db_values.get(key), _DEFAULTS[key]) for key in _KEYS
    }
    m = counts_row._mapping if counts_row is not None else {}
    return JSONResponse({
        'values': values,
        'defaults': dict(_DEFAULTS),
        'rows_missing': [k for k in _KEYS if k not in db_values],
        'stats': {
            'total': int(m.get('total') or 0),
            'pending': int(m.get('pending') or 0),
            'paid': int(m.get('paid') or 0),
            'capped': int(m.get('capped') or 0),
            'total_paid_toman': int(m.get('total_paid_toman') or 0),
        },
    })


@router.put('/admin/referral/settings')
async def update_referral_settings(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Write one or more of the three referral numbers.
    ``{"referral_reward_toman": 5000, ...}``; each field optional, each a
    non-negative integer within its bound."""
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'The database is unavailable.', 500)

    if not isinstance(payload, dict) or not payload:
        return err(
            'هیچ فیلدی برای بروزرسانی ارسال نشده است',
            'No field was sent to update.', 400,
        )

    unknown = set(payload) - set(_FIELD_TO_KEY)
    if unknown:
        return err(
            f'کلید ناشناخته: {", ".join(sorted(unknown))}',
            f'Unknown key: {", ".join(sorted(unknown))}', 400,
        )

    cleaned: dict[str, int] = {}
    for field, key in _FIELD_TO_KEY.items():
        if field not in payload:
            continue
        raw = payload[field]
        # Reject non-integers explicitly rather than coercing -- an admin
        # who types "3.5" or "abc" must see an error, not a silently
        # floored/truncated payout amount.
        if isinstance(raw, bool) or not isinstance(raw, int):
            if isinstance(raw, str) and raw.strip().lstrip('-').isdigit():
                raw = int(raw.strip())
            else:
                return err(
                    f'مقدار {field} باید یک عدد صحیح باشد',
                    f'The {field} value must be an integer.', 400,
                )
        lo, hi = _BOUNDS[key]
        if raw < lo or raw > hi:
            return err(
                f'مقدار {field} باید بین {lo} و {hi} باشد',
                f'The {field} value must be between {lo} and {hi}.', 400,
            )
        cleaned[key] = raw

    if not cleaned:
        return err(
            'هیچ فیلدی برای بروزرسانی ارسال نشده است',
            'No field was sent to update.', 400,
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
        logger.warning('PUT /admin/referral/settings DB write failed: %s', e)
        return err(
            'خطا در ذخیرهٔ تنظیمات در پایگاه داده',
            'Failed to save settings to the database.', 500,
        )

    invalidate()

    await _write_audit_log(
        'admin.referral_settings.update', target_type='referral_setting',
        target_id=','.join(sorted(cleaned)) if len(cleaned) > 1 else next(iter(cleaned)),
        details=dict(cleaned), request=request,
    )
    return JSONResponse({'status': 'ok', 'updated': cleaned})
