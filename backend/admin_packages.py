"""
Admin endpoints for `credit_packages` -- GapGPT-style packages.

Buying a package tops up the wallet with Toman (as it always has) and, as of
migration 0034, can *also* grant a quota of requests and/or tokens counted
separately from Toman. Before this file, admins had no UI for
`credit_packages` at all beyond raw SQL.

── Read this before touching money fields on credit_packages ──────────────

migration 0049 dropped the legacy pre-rename trio (`price`, `credits`,
`bonus_credits`) plus `name` -- they predated the checkout flow now in
pricing.py/payment_endpoints.py, nothing had read them since migration
0018, and this router no longer accepts or writes them. What
pricing.py's credit_package_checkout() charges via Zarinpal, and
payment_endpoints.py's payment_callback() actually credits to the wallet,
are the only money fields left:

    `base_amount`  -- Toman charged.
    `bonus_percent` -- display-only percentage.
    `total_credits` -- Toman credited to the wallet on success. This is
                        already the post-bonus total, not
                        `base_amount + bonus_percent` applied again.

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

# Field tables, payload parsing and the loss-path rule live in a sibling
# module -- this file is the endpoints. See admin_packages_validation.py.
from admin_packages_validation import (  # noqa: E402
    _ALL_MONEY_FIELDS, _CEILING_FIELD, _EDITABLE_FIELDS,
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


# ── GET /admin/purchases (new -- see this packet's item 9) ─────────────────
#
# A completed credit-package purchase is a `payments` row with
# `payment_type = 'credit_package'` and `status = 'completed'` (see
# services/billing.py::mark_payment_completed and payment_endpoints.py's
# callback, both outside this file's ownership -- read, never edited, to
# confirm this shape). `reference_id` on that row is the `credit_packages.id`
# the buyer purchased (payment_endpoints.py sets it before checkout; the FK
# is soft -- a package could theoretically be deleted after purchase, hence
# the LEFT JOIN and nullable package_* fields below rather than an INNER
# JOIN that would silently drop such a row from the admin's view).
#
# Field names deliberately match frontend/app/admin/sections/
# PurchasesSection.tsx's provisional `PurchaseRow` guess (`email`, `name_fa`,
# `name_en`, `total_credits`) where that guess lines up with a real column,
# to minimize the frontend agent's rework once this contract is reported.
# No `gateway` field: Sanjabai has exactly one payment gateway (Zarinpal)
# and `payments` carries no column naming it -- fabricating a hardcoded
# string here would be a fact this endpoint doesn't actually know.
#
# Literal SQL inside text() -- never an f-string here (sql_schema_audit.py
# cannot EXPLAIN an f-string query and drops it to "manual review", and this
# suite mocks the database so a wrong column name would otherwise have no
# guard at all until production).
_PURCHASES_SQL = sqlalchemy.text('''
    SELECT p.id, p.user_id, u.email, u.phone,
           p.reference_id AS package_id, cp.name_fa, cp.name_en,
           p.amount, cp.total_credits, p.status,
           p.created_at, p.verified_at
    FROM payments p
    JOIN users u ON u.id = p.user_id
    LEFT JOIN credit_packages cp ON cp.id = p.reference_id
    WHERE p.payment_type = 'credit_package' AND p.status = 'completed'
    ORDER BY p.verified_at DESC NULLS LAST, p.created_at DESC
    LIMIT :limit OFFSET :offset
''')

_PURCHASES_COUNT_SQL = sqlalchemy.text('''
    SELECT COUNT(*) AS c FROM payments
    WHERE payment_type = 'credit_package' AND status = 'completed'
''')


@router.get('/admin/purchases')
async def list_purchases(request: Request) -> JSONResponse:
    """Completed credit-package purchases, buyer-joined, paginated.

    Response envelope is pinned by the senior for a frontend agent building
    against it -- see this packet's item 9:
    ``{"purchases": [...], "total": <int>, "page": <int>, "limit": <int>}``.
    Each item carries: id, user_id, email, phone, package_id, name_fa,
    name_en, amount (Toman charged), total_credits (Toman credited to the
    wallet), status, created_at, verified_at. Pagination idiom (page/limit
    query params, limit capped at 200) mirrors admin_users.py's
    `/admin/users` list.
    """
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    page = int(request.query_params.get('page', 1))
    limit = min(int(request.query_params.get('limit', 50)), 200)
    offset = (page - 1) * limit

    async with async_session() as session:
        count_res = await session.execute(_PURCHASES_COUNT_SQL)
        total = count_res.fetchone().c
        res = await session.execute(_PURCHASES_SQL, {'limit': limit, 'offset': offset})
        rows = [dict(r._mapping) for r in res.fetchall()]

    return JSONResponse(jsonable_encoder({
        'purchases': rows, 'total': total, 'page': page, 'limit': limit,
    }))


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

    The legacy trio (`name`, `price`, `credits`, `bonus_credits`) that used
    to force filler defaults here is gone -- migration 0049 dropped those
    columns entirely (plans/subscriptions retired), so this endpoint no
    longer writes to them at all.
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
