"""Premium (expensive-model) sub-allowance gate, scaled by the user's
package (migration 0046, ``credit_packages.premium_rate_limit_per_window``).

── WHO THIS APPLIES TO ─────────────────────────────────────────────────────
Only a user holding an active, unexpired package whose
``premium_rate_limit_per_window`` is set. Everyone else is EXEMPT from THIS
gate specifically:

  * A package-less paid/wallet user pays per request via
    BillingService.reserve(); this gate is not the money guard, so it has
    nothing to add for them.
  * A free user (no package, no balance, never paid) cannot reach an
    expensive model at all -- services/free_tier.py's cheap-models-only
    check already refuses any model whose base input price is above
    ``free_tier_max_input_per_million``, before this gate would ever run.
  * A package holder whose ``premium_rate_limit_per_window`` is NULL (every
    package today) is exempt from THIS gate too, even though they may still
    be capped by services/user_quota.py's separate aggregate rate limit.

Exemption is resolved via services/user_quota.py::premium_package_window_limit
-- the identical best-active-package tiering logic user_quota.py already
implements for its own ``rate_limit_per_window`` column, reused here rather
than reimplemented (see that module's docstring for why both queries share
one helper).

── WHAT COUNTS AS "EXPENSIVE" ──────────────────────────────────────────────
A model whose BASE input price (``model_catalog.input_per_million``) is
STRICTLY GREATER THAN the admin-tunable ``premium_model_min_input_per_million``
setting (migration 0046, default 150000 Toman/M). Compared against the base
price, never the marked-up price actually charged to the user -- the same
choice services/free_tier.py makes for its own cheap-model ceiling (see
free_tier.py's ``_model_input_price``/cheap-model check). The reason matters:
the served price moves with ``global_markup_pct`` (content.py's
``get_global_markup_pct``/``apply_markup``), and if this gate compared that
instead, an admin raising the global markup would silently reclassify
ordinary models as premium without ever touching this setting. A model
absent from the catalog (unknown price) is NOT treated as expensive --
"cannot confirm expensive" fails open, consistent with the rest of this
gate and with free_tier.py's identical choice.

── ORDER ────────────────────────────────────────────────────────────────
Runs POST-MODEL-RESOLUTION -- it needs the model's price, so unlike
services/user_quota.py (pre-model, aggregate, no model in scope yet) it
must be called after the model id is resolved, exactly where
services/free_tier.py's check_and_consume already runs: after the free-tier
gate, strictly before BillingService.reserve(). See chat_web.py's wiring
inside chat_with_file for the exact call site this session owns; the other
three chat entry points (chat.py, chat_smart.py, chat_compare.py) need the
identical wiring at their own free-tier-gate call sites by whoever owns
those files.

One HTTP request = one message, aggregated across every model in the
request -- same rule as user_quota.py/free_tier.py. /v1/compare's two
models both count toward whether the request is "premium" (if EITHER model
in the request is expensive, the whole request is charged against the
premium sub-allowance), but the counter itself is still incremented by ONE
per HTTP request, never per model.

A request that touches no expensive model consumes NOTHING from this
gate's counter -- it simply is not a premium request, so the premium
allowance is not the resource being spent.

── WINDOWING ────────────────────────────────────────────────────────────
Same fixed-5-hour bucket as user_quota.py/free_tier.py: key
``premiumquota:msg:{uid}`` is INCRBY'd, and the FIRST message of a bucket
sets EXPIRE 18000 (WINDOW_SECONDS). Anchored at that first message, not
rolling -- an attempt made while the count already sits at the limit is
rejected without touching the counter, and the key's remaining TTL is what
is handed back as the retry countdown.

── PEEK-THEN-CONSUME ────────────────────────────────────────────────────
Same two-phase shape as free_tier.py/user_quota.py, in that order: the read
decides, the write only happens once the decision is "allow". A rejected
request burns nothing. Do NOT move the INCRBY before the check -- see
user_quota.py's identical warning for why (an INCRBY-first-then-refund
shape would burn budget on every rejection, which is worse than the small
overshoot two concurrent requests can cause under peek-then-consume).

── FAIL-OPEN ────────────────────────────────────────────────────────────
Any Redis or DB error anywhere in :func:`check_and_consume` is logged as a
warning and the request is ALLOWED, exactly like its two siblings. Money is
protected by BillingService.reserve() on every path regardless of what this
gate decides -- availability wins here, the premium-model nudge does not.

── THE REJECTION MESSAGE ────────────────────────────────────────────────
Persian, and deliberately vague about mechanism: it says the advanced-model
allowance for this window is full, how long until it refreshes, and that
other (non-premium) models still work. It never names a rule, a model, a
provider, or an upstream -- a normal user should never learn this product
routes through multiple providers or that "premium" is a price-based
classification at all.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import sqlalchemy

from database import async_session, rds
from dependencies import _to_fa
from services.user_quota import premium_package_window_limit

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 18000  # 5 hours, same bucket length as user_quota.py/free_tier.py

# Fail-safe default, MUST equal migration 0046's seed so behaviour is
# identical whether or not the migration has run yet.
DEFAULT_MIN_INPUT_PER_MILLION = 150000

_SETTING_KEY = 'premium_model_min_input_per_million'
_CACHE_TTL = 60  # seconds; same spirit as services/free_tier_config.py
_cache_value: Optional[int] = None
_cache_at: float = 0.0

_SETTING_SQL = sqlalchemy.text(
    'SELECT value FROM app_setting WHERE key = :key'
)

# Base input price (Toman per million) for a resolved provider_model_id.
# Local copy of free_tier.py's identical query -- kept here rather than
# imported so this module has no runtime dependency on free_tier.py's
# private names, matching the isolation free_tier.py itself already applies
# to its own local copy of a Persian-duration helper (see its docstring).
_MODEL_PRICE_SQL = sqlalchemy.text(
    "SELECT input_per_million FROM model_catalog "
    "WHERE provider_model_id = :m LIMIT 1"
)


def _msg_key(uid: int) -> str:
    return f'premiumquota:msg:{uid}'


def _fa_duration(seconds: int) -> str:
    """Persian countdown for the throttle message. A local copy of the same
    shape chat.py::_persian_duration and free_tier.py::_fa_duration already
    use, rather than importing across modules for one formatter."""
    seconds = max(int(seconds), 0)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours and minutes:
        return f'{_to_fa(hours)} ساعت و {_to_fa(minutes)} دقیقه'
    if hours:
        return f'{_to_fa(hours)} ساعت'
    if minutes:
        return f'{_to_fa(minutes)} دقیقه'
    return f'{_to_fa(max(seconds, 1))} ثانیه'


def invalidate_setting_cache() -> None:
    """Drop the cached threshold so the next read reflects a just-written
    admin change. Not currently called by any admin endpoint (this session
    does not own one) -- exposed so a future admin panel wiring this
    setting can invalidate it the same way admin_free_tier.py does for
    services/free_tier_config.py."""
    global _cache_value, _cache_at
    _cache_value = None
    _cache_at = 0.0


async def _min_input_per_million() -> int:
    """The admin-tunable expensive-model price ceiling, cached for 60s.
    Fails safe to :data:`DEFAULT_MIN_INPUT_PER_MILLION` if app_setting is
    unreadable, malformed, or the migration has not run yet -- never
    raises, and never treats "unreadable" as "no ceiling"."""
    global _cache_value, _cache_at
    now = time.monotonic()
    if _cache_value is not None and (now - _cache_at) < _CACHE_TTL:
        return _cache_value

    value = DEFAULT_MIN_INPUT_PER_MILLION
    try:
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(_SETTING_SQL, {'key': _SETTING_KEY})
                row = res.fetchone()
                if row is not None:
                    raw = row._mapping['value']
                    if isinstance(raw, str):
                        raw = json.loads(raw)
                    n = int(raw)
                    if n >= 0:
                        value = n
    except Exception as e:
        logger.warning(f"premium_quota._min_input_per_million load failed, using default: {e}")
        value = DEFAULT_MIN_INPUT_PER_MILLION

    _cache_value = value
    _cache_at = now
    return value


async def _model_input_price(model: str) -> Optional[int]:
    """Base input price (Toman/M) for a resolved provider_model_id, or None
    if the model is not in the catalog (or the lookup failed)."""
    try:
        if async_session is None:
            return None
        async with async_session() as session:
            res = await session.execute(_MODEL_PRICE_SQL, {'m': model})
            row = res.fetchone()
            if row is None:
                return None
            value = row._mapping['input_per_million']
            return int(value) if value is not None else None
    except Exception as e:
        logger.warning(f"premium_quota._model_input_price failed model={model}: {e}")
        return None


async def _is_expensive(model: str, threshold: int) -> bool:
    """True iff ``model``'s BASE input price is strictly greater than
    ``threshold``. An unknown price fails open to False -- "cannot confirm
    expensive" -- consistent with free_tier.py's identical choice."""
    price = await _model_input_price(model)
    if price is None:
        return False
    return price > threshold


async def check_and_consume(uid: int, models: list[str]) -> Optional[dict]:
    """Apply the premium sub-allowance to a chat request for ``models`` and,
    only if the user is capped AND at least one model is expensive AND the
    window has room, consume one message. Returns ``None`` when allowed (or
    when this gate simply does not apply to this user/request); otherwise a
    gate dict ``{'code', 'model', 'retry_after_seconds', 'message'}`` and
    NOTHING is consumed.

    Fails open: any Redis/DB error is logged and treated as an allow.
    """
    try:
        limit = await premium_package_window_limit(uid)
        if limit is None:
            # No package grants a premium sub-allowance -> this gate does
            # not apply to this user at all. See module docstring.
            return None

        threshold = await _min_input_per_million()
        expensive_model = None
        for model in models:
            if await _is_expensive(model, threshold):
                expensive_model = model
                break
        if expensive_model is None:
            # None of this request's models are premium -> nothing to gate
            # and nothing to consume; the allowance is untouched.
            return None

        key = _msg_key(uid)

        # Phase 1 -- peek. Nothing is mutated on the rejection path.
        raw = await rds.get(key)
        used = int(raw) if raw is not None else 0
        if used + 1 > limit:
            ttl = await rds.ttl(key)
            if ttl is None or ttl < 0:
                # At the cap with no expiry set: the bucket would never
                # reset and there is no honest countdown to report, so fail
                # open rather than trap the user behind a dead key. Same
                # reasoning as free_tier.py/user_quota.py's identical branch.
                logger.warning(
                    f"premium_quota: uid={uid} at cap ({used}/{limit}) with no TTL, failing open"
                )
                return None
            return {
                'code': 'premium_quota_exceeded',
                'model': expensive_model,
                'retry_after_seconds': int(ttl),
                'message': (
                    'سهم مدل‌های پیشرفته حساب شما برای این بازه به پایان رسیده '
                    f'است. حدود {_fa_duration(int(ttl))} دیگر دوباره فعال '
                    'می‌شود. مدل‌های دیگر همچنان در دسترس شما هستند.'
                ),
            }

        # Phase 2 -- consume. The first premium message of a bucket anchors
        # the 5-hour window; a key that somehow lost its TTL gets one back
        # rather than living forever.
        new_count = await rds.incrby(key, 1)
        if new_count <= 1:
            await rds.expire(key, WINDOW_SECONDS)
        else:
            ttl = await rds.ttl(key)
            if ttl is None or ttl < 0:
                await rds.expire(key, WINDOW_SECONDS)

        return None
    except Exception as e:
        logger.warning(f"premium_quota.check_and_consume failed uid={uid} models={models}: {e}")
        return None
