"""
Admin endpoints for `credit_packages` -- GapGPT-style packages.

Buying a package tops up the wallet with Toman (as it always has) and, as of
migration 0034, can *also* grant a quota of requests and/or tokens counted
separately from Toman. Before this file, admins had no UI for
`credit_packages` at all beyond raw SQL.

── Read this before touching money fields on credit_packages ──────────────

The table carries two generations of the same idea, and both are live in
the schema today, so this router edits both -- but only the second group is
what a purchase actually reads:

  legacy (predates the checkout flow now in pricing.py/payment_endpoints.py):
    `price`, `credits`, `bonus_credits`, `name`. A repo-wide grep for reads
    of CreditPackage.price / .credits / .bonus_credits / the `name` column,
    outside of raw `SELECT *`-style admin listings (this file included and
    admin.py's older `/admin/credit-packages`), found none. Nothing in the
    purchase or credit path consults them.

  live (what pricing.py's credit_package_checkout() charges via Zarinpal,
  and payment_endpoints.py's payment_callback() actually credits to the
  wallet):
    `base_amount`  -- Toman charged.
    `bonus_percent` -- display-only percentage.
    `total_credits` -- Toman credited to the wallet on success. This is
                        already the post-bonus total; it is NOT
                        `credits + bonus_credits` on top of it, and the
                        legacy `credits`/`bonus_credits` pair is not summed
                        with anything live. Reading the seed data confirms
                        this: pro-credits has base_amount=500000,
                        bonus_percent=10, total_credits=550000 -- and also
                        credits=550000, bonus_credits=50000, i.e. `credits`
                        already equals `total_credits`; treating
                        `credits + bonus_credits` as "what's credited" (as
                        a naive reading of the two column names suggests)
                        would double the bonus to 600000, which is not what
                        payment_endpoints.py actually does.

Both groups stay editable here (parity with the field list this file was
speced against, and with admin.py's older endpoint), but the legacy trio is
cosmetic: editing it does not change what a future buyer pays or receives.
The frontend must make that visible rather than presenting all money fields
as equally load-bearing.

If a package's price is edited after purchases already happened at the old
price, those existing entitlements/wallet credits are unaffected -- a
purchase captures its own numbers at checkout time (Payment.amount, and the
entitlement/quota granted at grant time); this endpoint only changes what a
*future* purchase reads. Nobody should later "fix" old entitlements to
match a new price.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session
from dependencies import admin_required, _write_audit_log
from i18n import err

logger = logging.getLogger(__name__)

router = APIRouter()

# Legacy money columns: NOT NULL in the DB, no product meaning today (see
# module docstring). Still editable for parity with admin.py's older
# endpoint, but never required from a caller and never defaulted from a
# live field except on create, where the NOT NULL constraint forces *some*
# value.
# Field tables, payload parsing and the loss-path rule live in a sibling
# module -- this file is the endpoints. See admin_packages_validation.py.
from admin_packages_validation import (  # noqa: E402
    _ALL_MONEY_FIELDS, _CEILING_FIELD, _EDITABLE_FIELDS, _LEGACY_MONEY_FIELDS,
    _LIVE_MONEY_FIELDS, _MONEY_LABELS, _PERCENT_FIELD, _QUOTA_FIELDS,
    _QUOTA_LABELS, _RATE_LIMIT_FIELDS, _RATE_LIMIT_LABELS, _TEXT_FIELDS,
    _check_loss_path, _parse_int_field, _validate_payload,
)


@router.get('/admin/packages')
async def list_packages(request: Request) -> JSONResponse:
    """All credit packages, every column, for the admin packages table."""
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text('SELECT * FROM credit_packages ORDER BY sort_order, id'))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/packages/{package_id}')
async def update_package(request: Request, package_id: str, payload: dict[str, Any]) -> JSONResponse:
    """Update the editable fields of one credit package.

    Server-side validation is authoritative -- the admin UI's own warnings
    are a convenience, not the guard. Every accepted change is written to
    the audit log; pricing is money and every edit must be traceable.
    """
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    unknown = set(payload) - set(_EDITABLE_FIELDS)
    if unknown:
        return err(f'فیلد ناشناخته: {", ".join(sorted(unknown))}',
                    f'Unknown field(s): {", ".join(sorted(unknown))}', 400)

    # Named `error`, not `err`, so it never shadows the `err()` import used above/below.
    cleaned, error = _validate_payload(payload)
    if error:
        return JSONResponse({'detail': error}, status_code=400)
    if not cleaned:
        return err('هیچ فیلدی برای بروزرسانی ارسال نشده است', 'No fields were submitted to update.', 400)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM credit_packages WHERE id = :pid'), {'pid': package_id}
        )
        current = res.fetchone()
        if not current:
            return err('بسته یافت نشد', 'Package not found.', 404)
        current_map = dict(current._mapping)

        effective = {**current_map, **cleaned}
        loss_err = _check_loss_path(effective)
        if loss_err:
            return err(loss_err[0], loss_err[1], 400)

        set_parts = [f'{f} = :{f}' for f in cleaned]
        set_parts.append('updated_at = now()')
        params = {**cleaned, 'pid': package_id}
        await session.execute(
            sqlalchemy.text(f"UPDATE credit_packages SET {', '.join(set_parts)} WHERE id = :pid"),
            params,
        )
        await session.commit()

    await _write_audit_log(
        'admin.package.update', target_type='credit_package', target_id=package_id,
        details=cleaned, request=request,
    )
    return JSONResponse({'status': 'ok', 'id': package_id, 'updated': cleaned})


@router.post('/admin/packages')
async def create_package(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Create a new credit package.

    The legacy trio (`name`, `price`, `credits`) is NOT NULL with no
    default, so a create must supply real values for it even though it has
    no effect on checkout -- this defaults it from the live fields
    (`name_en`/`base_amount`/`total_credits`) when the caller doesn't
    supply it explicitly, purely to satisfy the constraint, not because it
    means anything.
    """
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    package_id = str(payload.get('id') or '').strip()
    if not package_id or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', package_id):
        return err('شناسهٔ بسته الزامی است (حروف/اعداد کوچک انگلیسی، خط تیره یا زیرخط)',
                    'Package ID is required (lowercase English letters/digits, hyphen or underscore).', 400)

    unknown = set(payload) - set(_EDITABLE_FIELDS) - {'id'}
    if unknown:
        return err(f'فیلد ناشناخته: {", ".join(sorted(unknown))}',
                    f'Unknown field(s): {", ".join(sorted(unknown))}', 400)

    if not str(payload.get('name_fa') or '').strip():
        return err('نام فارسی الزامی است', 'The Persian name is required.', 400)
    if not str(payload.get('name_en') or '').strip():
        return err('نام انگلیسی الزامی است', 'The English name is required.', 400)

    # Named `error`, not `err`, so it never shadows the `err()` import used above.
    cleaned, error = _validate_payload({k: v for k, v in payload.items() if k != 'id'})
    if error:
        return JSONResponse({'detail': error}, status_code=400)

    # Satisfy the NOT-NULL-no-default legacy columns from the live fields
    # when not explicitly given -- see docstring.
    cleaned.setdefault('name', cleaned.get('name_en'))
    cleaned.setdefault('price', cleaned.get('base_amount', 0))
    cleaned.setdefault('credits', cleaned.get('total_credits', cleaned.get('base_amount', 0)))
    cleaned.setdefault('bonus_credits', 0)
    cleaned.setdefault('active', True)

    loss_err = _check_loss_path(cleaned)
    if loss_err:
        return err(loss_err[0], loss_err[1], 400)

    async with async_session() as session:
        existing = await session.execute(
            sqlalchemy.text('SELECT id FROM credit_packages WHERE id = :pid'), {'pid': package_id}
        )
        if existing.fetchone():
            return err('این شناسه قبلاً استفاده شده است', 'This ID is already in use.', 400)

        columns = list(cleaned.keys())
        await session.execute(
            sqlalchemy.text(
                f"INSERT INTO credit_packages (id, {', '.join(columns)}) "
                f"VALUES (:pid, {', '.join(f':{c}' for c in columns)})"
            ),
            {**cleaned, 'pid': package_id},
        )
        await session.commit()

    await _write_audit_log(
        'admin.package.create', target_type='credit_package', target_id=package_id,
        details=cleaned, request=request,
    )
    return JSONResponse({'status': 'ok', 'id': package_id, 'created': cleaned}, status_code=201)


# ── Premium-model price threshold (app_setting, migration 0046) ────────────
# A model counts as "expensive" for `premium_rate_limit_per_window` above
# when `model_catalog.input_per_million` is STRICTLY GREATER than this many
# Toman/M -- the comparison side lives wherever the rate-limit gate reads
# model_catalog, not here; this router only owns the admin-editable number.
# Shape mirrors admin_free_tier.py's GET/POST pair for a single value.
# Routed top-level (`/admin/premium-threshold`), NOT under
# `/admin/packages/...`, since `POST /admin/packages/{package_id}` above
# treats any path segment there as a package id and would silently collide.
# ⚠️ app_setting.value is JSONB, must hold a bare JSON integer
# (`json.dumps(150000)` -> `150000`), NOT a JSON string -- same convention
# as migration 0045 / admin_free_tier.py.
_PREMIUM_THRESHOLD_KEY = 'premium_model_min_input_per_million'
_PREMIUM_THRESHOLD_DEFAULT = 150_000  # must match migration 0046's seed
_PREMIUM_THRESHOLD_BOUNDS = (0, 100_000_000)  # same ceiling admin_free_tier.py uses

def _coerce_premium_threshold(value: Any) -> int:
    """Mirrors services/free_tier_config.py::_coerce_int for this one key --
    JSONB gives back a Python int already; a legacy JSON-string row is
    parsed once; anything else falls back to the seeded default."""
    try:
        if isinstance(value, str):
            value = json.loads(value)
        n = int(value)
        return n if n >= 0 else _PREMIUM_THRESHOLD_DEFAULT
    except Exception:
        return _PREMIUM_THRESHOLD_DEFAULT


@router.get('/admin/premium-threshold')
async def get_premium_threshold(request: Request) -> JSONResponse:
    """Current 'expensive model' price threshold. Direct DB read, no cache
    here, no fail-open: a DB error is a 500, never a guessed default shown
    as if it were the stored value."""
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text('SELECT value FROM app_setting WHERE key = :k'),
                {'k': _PREMIUM_THRESHOLD_KEY},
            )
            row = res.fetchone()
    except Exception as e:
        logger.warning('GET /admin/premium-threshold DB read failed: %s', e)
        return err('خطا در خواندن تنظیمات از پایگاه داده', 'Failed to read settings from the database.', 500)

    row_missing = row is None
    value = (
        _PREMIUM_THRESHOLD_DEFAULT if row_missing
        else _coerce_premium_threshold(row._mapping['value'])
    )
    return JSONResponse({
        'value': value,
        'default': _PREMIUM_THRESHOLD_DEFAULT,
        'row_missing': row_missing,
    })


@router.post('/admin/premium-threshold')
async def update_premium_threshold(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Write the threshold: ``{"value": 200000}`` -- one non-negative
    integer within bounds, stored as a bare JSON number."""
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    if not isinstance(payload, dict) or 'value' not in payload:
        return err('مقدار الزامی است', 'Value is required.', 400)

    raw = payload['value']
    # Reject non-integers explicitly (admin_free_tier.py's rule): "3.5" or
    # "abc" must error, never silently floor. bool excluded first -- it's
    # an int subclass in Python.
    if isinstance(raw, bool) or not isinstance(raw, int):
        if isinstance(raw, str) and raw.strip().lstrip('-').isdigit():
            raw = int(raw.strip())
        else:
            return err('مقدار باید یک عدد صحیح باشد', 'Value must be an integer.', 400)

    lo, hi = _PREMIUM_THRESHOLD_BOUNDS
    if raw < lo or raw > hi:
        return err(f'مقدار باید بین {lo} و {hi} باشد', f'Value must be between {lo} and {hi}.', 400)

    try:
        async with async_session() as session:
            await session.execute(
                sqlalchemy.text(
                    'INSERT INTO app_setting (key, value, updated_at) '
                    'VALUES (:k, :v, now()) '
                    'ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now()'
                ),
                {'k': _PREMIUM_THRESHOLD_KEY, 'v': json.dumps(raw)},
            )
            await session.commit()
    except Exception as e:
        logger.warning('POST /admin/premium-threshold DB write failed: %s', e)
        return err('خطا در ذخیرهٔ تنظیمات در پایگاه داده', 'Failed to save settings to the database.', 500)

    await _write_audit_log(
        'admin.premium_threshold.update', target_type='app_setting',
        target_id=_PREMIUM_THRESHOLD_KEY, details={'value': raw}, request=request,
    )
    return JSONResponse({'status': 'ok', 'value': raw})
