"""Field parsers for the catalog admin endpoints.

Split out of admin_catalog.py, which crossed the project's 500-line cap while
its refusals were being made bilingual. Pure parsing over one raw value each,
no router and no I/O.

WHY THE SHAPE IS WHAT IT IS. Both parsers return `(value, persian_error)` --
a 2-tuple, NOT a (value, fa, en) triple -- because tests/test_admin_image_price.py
and tests/test_admin_probe_gate.py call them directly and pin that shape. An
earlier pass changed them to triples and turned 13 tests red. The English half
therefore lives in the `_*_ERR_EN` maps below, keyed by the exact Persian
string, and the endpoint looks it up when building its `err()` call. Keep the
Persian keys and the returned strings byte-identical or the lookup silently
falls through to no translation.

admin_catalog.py re-imports both names, so `admin_catalog._parse_image_price`
still resolves for those tests.
"""
from __future__ import annotations

import re
from typing import Any

_MARKUP_PCT_MAX = 1000


def _parse_markup_pct(raw: Any, *, allow_null: bool) -> tuple[float | None, str | None]:
    """Validate a markup_pct payload value. Returns (value, error_detail).

    Kept a 2-tuple (Persian only) -- tests/test_admin_probe_gate.py's
    TestMarkupPctUpperCap and tests/test_markup.py call this directly and
    pin that exact shape. The English sibling for each of these four
    messages lives in `_MARKUP_PCT_ERR_EN` right below, keyed by the exact
    Persian string, so both languages are still visible together at this
    definition site -- callers translate via that map before handing the
    pair to `i18n.err()`.
    """
    if raw is None:
        if allow_null:
            return None, None
        return None, 'درصد سود الزامی است'
    try:
        pct = float(raw)
    except (TypeError, ValueError):
        return None, 'درصد نامعتبر است'
    if pct < 0:
        return None, 'درصد سود نمی‌تواند منفی باشد (هیچ درخواستی نباید ضررده باشد)'
    if pct > _MARKUP_PCT_MAX:
        return None, f'درصد سود بیش از حد مجاز است (سقف {_MARKUP_PCT_MAX:,}٪) -- احتمالاً اشتباه تایپی است'
    return pct, None


_MARKUP_PCT_ERR_EN = {
    'درصد سود الزامی است': 'Markup percentage is required.',
    'درصد نامعتبر است': 'Invalid percentage.',
    'درصد سود نمی‌تواند منفی باشد (هیچ درخواستی نباید ضررده باشد)':
        'Markup percentage cannot be negative (no request may be loss-making).',
    f'درصد سود بیش از حد مجاز است (سقف {_MARKUP_PCT_MAX:,}٪) -- احتمالاً اشتباه تایپی است':
        f'Markup percentage exceeds the allowed ceiling ({_MARKUP_PCT_MAX:,}%) -- likely a typo.',
}


def _parse_image_price(raw: Any) -> tuple[int | None, str | None]:
    """Validate an image_price_per_unit payload value.

    Returns (value, error_detail), Persian only -- tests/test_admin_image_price.py
    calls this directly and pins that 2-tuple shape. See `_IMAGE_PRICE_ERR_EN`
    right below for the English sibling of each message, keyed by the exact
    Persian string; callers translate via that map before handing the pair
    to `i18n.err()`.

    ``None`` (explicit null) clears the price back to "not set, cannot be
    served". Anything else must be an integer Toman amount >= 0. Floats are
    rejected outright -- including a JSON float that happens to be integral
    (``10.0``) and a bool (a subclass of ``int`` in Python, so
    ``isinstance(True, int)`` is True and ``True`` would otherwise silently
    parse as ``1``) -- so the only way to set a price is a JSON integer or a
    plain-digit string.
    """
    if raw is None:
        return None, None
    if isinstance(raw, bool) or isinstance(raw, float):
        return None, 'قیمت باید عدد صحیح تومان باشد (اعشار مجاز نیست)'
    if isinstance(raw, int):
        price = raw
    elif isinstance(raw, str) and re.fullmatch(r'-?\d+', raw.strip()):
        price = int(raw.strip())
    else:
        return None, 'قیمت باید عدد صحیح تومان باشد (اعشار مجاز نیست)'
    if price < 0:
        return None, 'قیمت نمی‌تواند منفی باشد'
    return price, None


_IMAGE_PRICE_ERR_EN = {
    'قیمت باید عدد صحیح تومان باشد (اعشار مجاز نیست)':
        'Price must be an integer toman amount (decimals not allowed).',
    'قیمت نمی‌تواند منفی باشد': 'Price cannot be negative.',
}
