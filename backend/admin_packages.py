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

logger = logging.getLogger(__name__)

router = APIRouter()

# Legacy money columns: NOT NULL in the DB, no product meaning today (see
# module docstring). Still editable for parity with admin.py's older
# endpoint, but never required from a caller and never defaulted from a
# live field except on create, where the NOT NULL constraint forces *some*
# value.
_LEGACY_MONEY_FIELDS = ('price', 'credits', 'bonus_credits')

# Live money columns: what pricing.py/payment_endpoints.py actually read.
_LIVE_MONEY_FIELDS = ('base_amount', 'total_credits')

# The loss-protection ceiling. Nullable; NULL means "no ceiling set yet".
_CEILING_FIELD = 'max_cost_per_request_toman'

# All Toman fields share the same "non-negative integer, no floats" rule.
_ALL_MONEY_FIELDS = _LEGACY_MONEY_FIELDS + _LIVE_MONEY_FIELDS + (_CEILING_FIELD,)

# migrations/0034_*: nullable quota fields. NULL means "this package does
# not grant that kind of quota". Positive-only when set -- a zero-request
# quota is meaningless and should just be NULL.
_QUOTA_FIELDS = ('request_quota', 'token_quota', 'validity_days')

# migrations/0046_*: nullable pure rate-limit fields, NULL = "no cap of that
# kind". Deliberately NOT part of _QUOTA_FIELDS and NOT wired into
# `_check_loss_path` below -- these never create a `package_entitlement`
# (see user_quota.py/chat_billing.py for what does), so the wallet always
# pays for what they gate; a ceiling requirement here would just re-couple
# a pure rate limit to the wallet-bypass entitlement the guard polices.
# `premium_rate_limit_per_window` is a subset counted from inside
# `rate_limit_per_window`, not an additional cap.
_RATE_LIMIT_FIELDS = ('rate_limit_per_window', 'premium_rate_limit_per_window')

_TEXT_FIELDS = ('name_fa', 'name_en', 'description', 'name')

_PERCENT_FIELD = 'bonus_percent'

# Every field this router will write if present in a request payload.
_EDITABLE_FIELDS = (
    _TEXT_FIELDS + _ALL_MONEY_FIELDS + _QUOTA_FIELDS + _RATE_LIMIT_FIELDS
    + (_PERCENT_FIELD, 'active')
)

def _parse_int_field(raw: Any, *, label: str, allow_null: bool, min_value: int) -> tuple[int | None, str | None]:
    """Shared integer guard for every money/quota field on this table.

    Rejects floats outright -- including an integral-looking one like
    ``10.0`` -- and rejects ``bool`` (a subclass of ``int`` in Python, so
    ``True`` would otherwise silently parse as ``1``). This is the only
    thing standing between an admin's request and a fractional Toman or a
    fractional quota entering the pricing/entitlement pipeline; never
    multiply or divide by 10 here or anywhere downstream.
    """
    if raw is None:
        if allow_null:
            return None, None
        return None, f'{label} الزامی است'
    if isinstance(raw, bool) or isinstance(raw, float):
        return None, f'{label} باید عدد صحیح باشد (اعشار مجاز نیست)'
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str) and re.fullmatch(r'-?\d+', raw.strip()):
        value = int(raw.strip())
    else:
        return None, f'{label} باید عدد صحیح باشد'
    if value < min_value:
        return None, f'{label} نمی‌تواند کمتر از {min_value} باشد'
    return value, None


_MONEY_LABELS = {
    'price': 'قیمت (ستون قدیمی)',
    'credits': 'اعتبار (ستون قدیمی)',
    'bonus_credits': 'اعتبار پاداش (ستون قدیمی)',
    'base_amount': 'مبلغ پرداختی',
    'total_credits': 'مبلغ واریزی به کیف پول',
    'max_cost_per_request_toman': 'سقف هزینه هر درخواست',
}
_QUOTA_LABELS = {
    'request_quota': 'سهمیهٔ تعداد درخواست',
    'token_quota': 'سهمیهٔ توکن',
    'validity_days': 'مدت اعتبار (روز)',
}
_RATE_LIMIT_LABELS = {
    'rate_limit_per_window': 'سقف پیام در هر پنجرهٔ ۵ ساعته',
    'premium_rate_limit_per_window': 'سقف پیام روی مدل‌های گران در هر پنجرهٔ ۵ ساعته',
}


def _validate_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Validate whichever editable fields are present in *payload*.

    Returns ``(cleaned, error)``: ``cleaned`` holds only the fields that
    were actually present, parsed to their final DB-ready value;
    ``error`` is a Persian message for the first validation failure, or
    ``None``. The loss-protection cross-field rule (quota without a
    ceiling) is deliberately NOT checked here -- it needs the *effective*
    row (payload merged over what's already in the DB), which only the
    caller can compute after fetching the current row.
    """
    cleaned: dict[str, Any] = {}

    for field in _ALL_MONEY_FIELDS:
        if field not in payload:
            continue
        # price/credits/bonus_credits are NOT NULL in the DB (no default on
        # price/credits); base_amount, total_credits and the ceiling are
        # nullable columns, so an explicit `null` legitimately clears them.
        allow_null = field not in _LEGACY_MONEY_FIELDS
        value, err = _parse_int_field(payload[field], label=_MONEY_LABELS[field], allow_null=allow_null, min_value=0)
        if err:
            return {}, err
        cleaned[field] = value

    for field in _QUOTA_FIELDS:
        if field not in payload:
            continue
        value, err = _parse_int_field(payload[field], label=_QUOTA_LABELS[field], allow_null=True, min_value=1)
        if err:
            return {}, err
        cleaned[field] = value

    # Same non-negative-integer, positive-only-when-set rule as the quota
    # fields above -- NULL means "no rate cap", zero is meaningless and
    # should just be NULL. See the field-group comment above _QUOTA_FIELDS:
    # deliberately not fed into `_check_loss_path`.
    for field in _RATE_LIMIT_FIELDS:
        if field not in payload:
            continue
        value, err = _parse_int_field(payload[field], label=_RATE_LIMIT_LABELS[field], allow_null=True, min_value=1)
        if err:
            return {}, err
        cleaned[field] = value

    if _PERCENT_FIELD in payload:
        value, err = _parse_int_field(payload[_PERCENT_FIELD], label='درصد پاداش', allow_null=True, min_value=0)
        if err:
            return {}, err
        cleaned[_PERCENT_FIELD] = value

    for field in _TEXT_FIELDS:
        if field not in payload:
            continue
        raw = payload[field]
        if field == 'description':
            cleaned[field] = None if raw is None else str(raw)
            continue
        if raw is None or not str(raw).strip():
            return {}, f'{"نام" if field != "description" else field} نمی‌تواند خالی باشد'
        cleaned[field] = str(raw)

    if 'active' in payload:
        if not isinstance(payload['active'], bool):
            return {}, 'وضعیت فعال بودن باید true/false باشد'
        cleaned['active'] = payload['active']

    return cleaned, None


def _check_loss_path(effective: dict[str, Any]) -> str | None:
    """🔴 The product's core loss-protection rule: a package that grants a
    request or token quota MUST carry a per-request cost ceiling, or a user
    could spend the whole quota on the most expensive model available and
    every one of those requests loses money. A request priced above the
    ceiling simply isn't covered by the quota and falls back to the wallet
    -- so the ceiling is not optional once either quota is set.

    Deliberately checks ONLY `request_quota`/`token_quota` -- do NOT extend
    this to `rate_limit_per_window`/`premium_rate_limit_per_window`
    (migration 0046, see `_RATE_LIMIT_FIELDS` above): those create no
    `package_entitlement` and the wallet always pays for what they gate, so
    there is no loss path here to close for them.
    """
    has_quota = effective.get('request_quota') is not None or effective.get('token_quota') is not None
    if has_quota and effective.get(_CEILING_FIELD) is None:
        return (
            'بسته‌ای که سهمیهٔ درخواست یا توکن دارد باید سقف هزینهٔ هر درخواست '
            '(max_cost_per_request_toman) هم داشته باشد، وگرنه مسیر ضررده است: '
            'کاربر می‌تواند کل سهمیه را روی گران‌ترین مدل خرج کند و هر درخواست ضرر بدهد.'
        )
    return None


@router.get('/admin/packages')
async def list_packages(request: Request) -> JSONResponse:
    """All credit packages, every column, for the admin packages table."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    unknown = set(payload) - set(_EDITABLE_FIELDS)
    if unknown:
        return JSONResponse({'detail': f'فیلد ناشناخته: {", ".join(sorted(unknown))}'}, status_code=400)

    cleaned, err = _validate_payload(payload)
    if err:
        return JSONResponse({'detail': err}, status_code=400)
    if not cleaned:
        return JSONResponse({'detail': 'هیچ فیلدی برای بروزرسانی ارسال نشده است'}, status_code=400)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM credit_packages WHERE id = :pid'), {'pid': package_id}
        )
        current = res.fetchone()
        if not current:
            return JSONResponse({'detail': 'بسته یافت نشد'}, status_code=404)
        current_map = dict(current._mapping)

        effective = {**current_map, **cleaned}
        loss_err = _check_loss_path(effective)
        if loss_err:
            return JSONResponse({'detail': loss_err}, status_code=400)

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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    package_id = str(payload.get('id') or '').strip()
    if not package_id or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', package_id):
        return JSONResponse(
            {'detail': 'شناسهٔ بسته الزامی است (حروف/اعداد کوچک انگلیسی، خط تیره یا زیرخط)'},
            status_code=400,
        )

    unknown = set(payload) - set(_EDITABLE_FIELDS) - {'id'}
    if unknown:
        return JSONResponse({'detail': f'فیلد ناشناخته: {", ".join(sorted(unknown))}'}, status_code=400)

    if not str(payload.get('name_fa') or '').strip():
        return JSONResponse({'detail': 'نام فارسی الزامی است'}, status_code=400)
    if not str(payload.get('name_en') or '').strip():
        return JSONResponse({'detail': 'نام انگلیسی الزامی است'}, status_code=400)

    cleaned, err = _validate_payload({k: v for k, v in payload.items() if k != 'id'})
    if err:
        return JSONResponse({'detail': err}, status_code=400)

    # Satisfy the NOT-NULL-no-default legacy columns from the live fields
    # when not explicitly given -- see docstring.
    cleaned.setdefault('name', cleaned.get('name_en'))
    cleaned.setdefault('price', cleaned.get('base_amount', 0))
    cleaned.setdefault('credits', cleaned.get('total_credits', cleaned.get('base_amount', 0)))
    cleaned.setdefault('bonus_credits', 0)
    cleaned.setdefault('active', True)

    loss_err = _check_loss_path(cleaned)
    if loss_err:
        return JSONResponse({'detail': loss_err}, status_code=400)

    async with async_session() as session:
        existing = await session.execute(
            sqlalchemy.text('SELECT id FROM credit_packages WHERE id = :pid'), {'pid': package_id}
        )
        if existing.fetchone():
            return JSONResponse({'detail': 'این شناسه قبلاً استفاده شده است'}, status_code=400)

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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text('SELECT value FROM app_setting WHERE key = :k'),
                {'k': _PREMIUM_THRESHOLD_KEY},
            )
            row = res.fetchone()
    except Exception as e:
        logger.warning('GET /admin/premium-threshold DB read failed: %s', e)
        return JSONResponse({'detail': 'خطا در خواندن تنظیمات از پایگاه داده'}, status_code=500)

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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    if not isinstance(payload, dict) or 'value' not in payload:
        return JSONResponse({'detail': 'مقدار الزامی است'}, status_code=400)

    raw = payload['value']
    # Reject non-integers explicitly (admin_free_tier.py's rule): "3.5" or
    # "abc" must error, never silently floor. bool excluded first -- it's
    # an int subclass in Python.
    if isinstance(raw, bool) or not isinstance(raw, int):
        if isinstance(raw, str) and raw.strip().lstrip('-').isdigit():
            raw = int(raw.strip())
        else:
            return JSONResponse({'detail': 'مقدار باید یک عدد صحیح باشد'}, status_code=400)

    lo, hi = _PREMIUM_THRESHOLD_BOUNDS
    if raw < lo or raw > hi:
        return JSONResponse({'detail': f'مقدار باید بین {lo} و {hi} باشد'}, status_code=400)

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
        return JSONResponse({'detail': 'خطا در ذخیرهٔ تنظیمات در پایگاه داده'}, status_code=500)

    await _write_audit_log(
        'admin.premium_threshold.update', target_type='app_setting',
        target_id=_PREMIUM_THRESHOLD_KEY, details={'value': raw}, request=request,
    )
    return JSONResponse({'status': 'ok', 'value': raw})
