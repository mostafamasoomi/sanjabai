"""Payload validation for the credit-package admin endpoints.

Split out of admin_packages.py, which crossed the project's 500-line cap while
its refusals were being made bilingual. The seam is clean: everything here is
pure validation over a dict -- no router, no session, no I/O -- and
admin_packages.py keeps only the endpoints.

Two things in here are load-bearing and are stated plainly so a future split
or refactor does not lose them:

* `_check_loss_path` returns a (persian, english) PAIR, not a string, and both
  `create_package` and `update_package` unpack it. It briefly returned a tuple
  while only ONE of those two call sites had been updated, which serialised a
  Python tuple straight into a `detail` field. The existing test asserted only
  the status code, so nothing caught it.

* Nothing in this module may name a local variable `err`. Modules that import
  the `err()` helper cannot, because Python binds a name assigned anywhere in
  a function as local for that whole function -- see
  tests/test_i18n_no_shadowing.py, which enforces this across the tree.
"""
from __future__ import annotations

import re
from typing import Any

# Live money columns: what pricing.py/payment_endpoints.py actually read.
# The legacy trio (`price`, `credits`, `bonus_credits`) that used to live
# here alongside these is gone -- migration 0049 dropped those columns
# entirely (plans/subscriptions retired), so this router no longer accepts
# or validates them.
_LIVE_MONEY_FIELDS = ('base_amount', 'total_credits')

# The loss-protection ceiling. Nullable; NULL means "no ceiling set yet".
_CEILING_FIELD = 'max_cost_per_request_toman'

# All Toman fields share the same "non-negative integer, no floats" rule.
_ALL_MONEY_FIELDS = _LIVE_MONEY_FIELDS + (_CEILING_FIELD,)

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

# The legacy `name` column (pre-rename original of name_fa/name_en) was
# dropped by migration 0049 along with the money trio above -- see this
# module's earlier comment. It is not an editable field any more.
#
# `model_id` (migration 0018): optional display metadata, "which model this
# bundle is framed around" -- nullable FK to model_catalog.id (ON DELETE SET
# NULL), does not change checkout math. Same nullable-text shape as
# `description`: NULL clears the label, an empty/blank string is not
# specially rejected here (the FK itself would reject an unknown model_id
# at the DB level).
_TEXT_FIELDS = ('name_fa', 'name_en', 'description', 'model_id')

# Text fields where NULL is a legitimate, meaningful value rather than "the
# caller forgot to fill this in" -- see the per-field loop in
# _validate_payload below.
_NULLABLE_TEXT_FIELDS = ('description', 'model_id')

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
        # base_amount, total_credits and the ceiling are all nullable
        # columns, so an explicit `null` legitimately clears them. (The
        # legacy NOT-NULL trio that used to force allow_null=False here is
        # gone -- migration 0049 dropped those columns.)
        value, perr = _parse_int_field(payload[field], label=_MONEY_LABELS[field], allow_null=True, min_value=0)
        if perr:
            return {}, perr
        cleaned[field] = value

    for field in _QUOTA_FIELDS:
        if field not in payload:
            continue
        value, perr = _parse_int_field(payload[field], label=_QUOTA_LABELS[field], allow_null=True, min_value=1)
        if perr:
            return {}, perr
        cleaned[field] = value

    # Same non-negative-integer, positive-only-when-set rule as the quota
    # fields above -- NULL means "no rate cap", zero is meaningless and
    # should just be NULL. See the field-group comment above _QUOTA_FIELDS:
    # deliberately not fed into `_check_loss_path`.
    for field in _RATE_LIMIT_FIELDS:
        if field not in payload:
            continue
        value, perr = _parse_int_field(payload[field], label=_RATE_LIMIT_LABELS[field], allow_null=True, min_value=1)
        if perr:
            return {}, perr
        cleaned[field] = value

    if _PERCENT_FIELD in payload:
        value, perr = _parse_int_field(payload[_PERCENT_FIELD], label='درصد پاداش', allow_null=True, min_value=0)
        if perr:
            return {}, perr
        cleaned[_PERCENT_FIELD] = value

    for field in _TEXT_FIELDS:
        if field not in payload:
            continue
        raw = payload[field]
        if field in _NULLABLE_TEXT_FIELDS:
            cleaned[field] = None if raw is None else str(raw)
            continue
        if raw is None or not str(raw).strip():
            return {}, 'نام نمی‌تواند خالی باشد'
        cleaned[field] = str(raw)

    if 'active' in payload:
        if not isinstance(payload['active'], bool):
            return {}, 'وضعیت فعال بودن باید true/false باشد'
        cleaned['active'] = payload['active']

    return cleaned, None


def _check_loss_path(effective: dict[str, Any]) -> tuple[str, str] | None:
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
            'کاربر می‌تواند کل سهمیه را روی گران‌ترین مدل خرج کند و هر درخواست ضرر بدهد.',
            'A package granting a request or token quota must also carry a '
            'per-request cost ceiling (max_cost_per_request_toman), or the path is '
            'loss-making: a user can spend the whole quota on the most expensive '
            'model and lose money on every request.',
        )
    return None
