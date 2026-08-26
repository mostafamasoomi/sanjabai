"""Free-tier gate: the limits for a user with no money and no package.

── WHO THIS APPLIES TO ─────────────────────────────────────────────────────
Only a user who has neither made a real gateway payment (:func:`has_paid`)
nor holds any wallet credit (:func:`has_balance`) nor holds a quota-granting
package (that tier is handled by services/user_quota.py). For everyone else
this gate returns None immediately -- a paying/package user is never touched
here.

── THE FREE TIER IS ACTUALLY FREE ──────────────────────────────────────────
A free user's messages are absorbed by the platform (they have no balance to
charge). That is why this gate exists and why it is strict: it is giving
model calls away. The owner's policy, all three limits admin-tunable via
services/free_tier_config.py (seeded by migration 0045, edited from
backend/admin_free_tier.py):

  1. CHEAP MODELS ONLY -- a free user may only send to a model whose base
     input price is at or below ``free_tier_max_input_per_million`` Toman/M.
     Checked FIRST, before anything is consumed, so a blocked premium request
     never burns the user's allowance.
  2. LIFETIME CAP -- ``free_lifetime_limit`` messages EVER (users.
     free_messages_used, a durable column -- a hard paywall must survive a
     Redis flush). Once spent, the user stays blocked until they pay.
  3. HOURLY CAP -- ``free_hourly_limit`` messages per rolling hour
     (Redis ``freetier:hourly:{uid}``, a fixed 1-hour bucket).

One HTTP request = one message, aggregated: /v1/compare fans out to two
models but costs ONE free message (both models must still be cheap). The
per-model bucket the old free tier used is gone.

── ORDER, AND WHY THE CHEAP CHECK IS FIRST ─────────────────────────────────
cheap-model  ->  lifetime  ->  hourly  ->  consume. All three checks are
peeks; nothing is consumed until every check has passed. So a free user who
picks a premium model, or who is already at their lifetime/hourly cap, loses
nothing from their remaining allowance -- the request is refused clean.

── has_paid / has_balance ──────────────────────────────────────────────────
"Has never paid" is resolved from the payment tables (``payments`` and the
legacy ``payment_orders``), never the ``ledger`` -- ledger txn_type cannot
tell a gateway payment from free money. has_balance reads the wallet
directly, which is a SOUND signal now that the signup gift and referral bonus
are gone (tests/test_credit_paths.py enforces that credit only comes from the
gateway or an admin), and it fixed a real bug where an account holding
9,954,787 Toman was told its credit had run out. has_paid is cached in Redis;
has_balance is not (a top-up must lift the throttle at once).

── Fail-open ───────────────────────────────────────────────────────────────
Any Redis or DB error anywhere in :func:`check_and_consume` is logged and the
request is ALLOWED. A storage hiccup must never lock out a user, and money is
independently protected by BillingService.reserve() on every path -- for a
free user on a cheap model the absorbed cost of one leaked message is
negligible. Availability wins here.
"""
from __future__ import annotations

import logging
from typing import Optional

import sqlalchemy

from database import async_session, rds
from dependencies import _to_fa
from services.free_tier_config import get_config

logger = logging.getLogger(__name__)

HOURLY_WINDOW_SECONDS = 3600  # the hourly bucket length

_PAID_TTL = 30 * 24 * 3600  # 30 days — paying never un-pays
_UNPAID_TTL = 300  # 5 minutes — re-check soon in case a payment just landed

_HAS_PAID_SQL = sqlalchemy.text(
    "SELECT 1 FROM payments WHERE user_id = :uid AND status = 'completed' "
    "UNION ALL "
    "SELECT 1 FROM payment_orders WHERE user_id = :uid AND status = 'completed' "
    "LIMIT 1"
)

_HAS_BALANCE_SQL = sqlalchemy.text(
    "SELECT 1 FROM wallet WHERE user_id = :uid AND balance > 0 LIMIT 1"
)

# Base input price (Toman per million) for a resolved provider_model_id. Used
# by the cheap-model gate. A model absent from the catalog returns no row ->
# the gate treats an unknown price as "cannot confirm expensive" and allows
# (fail-open), consistent with this module; such a model would fail downstream
# anyway and the frontend only ever offers a free user the cheap ones.
_MODEL_PRICE_SQL = sqlalchemy.text(
    "SELECT input_per_million FROM model_catalog "
    "WHERE provider_model_id = :m LIMIT 1"
)

# Durable lifetime counter (migration 0045). RETURNING lets the increment read
# back the new value in one round-trip so a concurrent request cannot race the
# read against a stale count.
_LIFETIME_READ_SQL = sqlalchemy.text(
    "SELECT free_messages_used FROM users WHERE id = :uid"
)
_LIFETIME_INCR_SQL = sqlalchemy.text(
    "UPDATE users SET free_messages_used = free_messages_used + 1 "
    "WHERE id = :uid RETURNING free_messages_used"
)


def _paid_key(uid: int) -> str:
    return f'freetier:paid:{uid}'


def _hourly_key(uid: int) -> str:
    return f'freetier:hourly:{uid}'


def _fa_duration(seconds: int) -> str:
    """Persian countdown for a throttle message (e.g. 2400 -> "۴۰ دقیقه").
    A local copy rather than importing chat._persian_duration, which would be
    circular (chat imports this module)."""
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


async def has_balance(uid: int) -> bool:
    """True if the user currently holds any wallet credit. Not cached (a
    top-up must lift the throttle at once). Fails CLOSED to False on error,
    matching has_paid -- an unreadable balance falls back to the free-tier
    gate rather than silently granting unlimited access."""
    try:
        if async_session is None:
            return False
        async with async_session() as session:
            res = await session.execute(_HAS_BALANCE_SQL, {'uid': uid})
            return res.fetchone() is not None
    except Exception as e:
        logger.warning(f"free_tier.has_balance check failed uid={uid}: {e}")
        return False


async def has_paid(uid: int) -> bool:
    """True iff the user has ever completed a real gateway payment. Cached in
    Redis. On any Redis/DB error logs and returns False (apply the gate)."""
    key = _paid_key(uid)
    try:
        cached = await rds.get(key)
        if cached == '1':
            return True
        if cached == '0':
            return False
    except Exception as e:
        logger.warning(f"free_tier.has_paid cache read failed uid={uid}: {e}")

    paid = False
    try:
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(_HAS_PAID_SQL, {'uid': uid})
                paid = res.fetchone() is not None
    except Exception as e:
        logger.warning(f"free_tier.has_paid db check failed uid={uid}: {e}")
        return False

    try:
        if paid:
            await rds.set(key, '1', ex=_PAID_TTL)
        else:
            await rds.set(key, '0', ex=_UNPAID_TTL)
    except Exception as e:
        logger.warning(f"free_tier.has_paid cache write failed uid={uid}: {e}")

    return paid


async def _model_input_price(model: str) -> Optional[int]:
    """Base input price (Toman/M) for a resolved provider_model_id, or None if
    the model is not in the catalog (or the lookup failed)."""
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
        logger.warning(f"free_tier._model_input_price failed model={model}: {e}")
        return None


async def _lifetime_used(uid: int) -> Optional[int]:
    """Durable lifetime free-message count, or None if unreadable."""
    try:
        if async_session is None:
            return None
        async with async_session() as session:
            res = await session.execute(_LIFETIME_READ_SQL, {'uid': int(uid)})
            row = res.fetchone()
            if row is None:
                return None
            return int(row._mapping['free_messages_used'])
    except Exception as e:
        logger.warning(f"free_tier._lifetime_used failed uid={uid}: {e}")
        return None


async def _lifetime_incr(uid: int) -> None:
    """Increment the durable lifetime counter by one. Swallows its own error
    (the caller's fail-open handler covers the request); a lost increment
    means at worst one extra free message, never a wrongful block."""
    try:
        if async_session is None:
            return
        async with async_session() as session:
            await session.execute(_LIFETIME_INCR_SQL, {'uid': int(uid)})
            await session.commit()
    except Exception as e:
        logger.warning(f"free_tier._lifetime_incr failed uid={uid}: {e}")


async def check_and_consume(uid: int, models: list[str]) -> Optional[dict]:
    """Apply the free tier to a chat request for ``models`` and, only if all
    three limits pass, consume one message. Returns ``None`` when allowed;
    otherwise a gate dict ``{'code', 'message', 'retry_after_seconds',
    'model'}`` and NOTHING is consumed.

    Fails open: any Redis/DB error is logged and treated as an allow.
    """
    try:
        if await has_paid(uid):
            return None
        if await has_balance(uid):
            return None

        cfg = await get_config()
        hourly_limit = int(cfg['free_hourly_limit'])
        lifetime_limit = int(cfg['free_lifetime_limit'])
        max_input = int(cfg['free_tier_max_input_per_million'])

        # ── Check 1: cheap models only (before anything is consumed) ──
        for model in models:
            price = await _model_input_price(model)
            if price is not None and price > max_input:
                return {
                    'code': 'free_model_not_allowed',
                    'model': model,
                    'retry_after_seconds': 0,
                    'message': (
                        'این مدل برای حساب رایگان در دسترس نیست. برای استفاده از '
                        'مدل‌های پیشرفته لطفاً حساب خود را شارژ کنید؛ مدل‌های '
                        'اقتصادی همچنان به‌صورت رایگان در اختیار شماست.'
                    ),
                    'message_en': (
                        'This model is not available on a free account. Top up to use '
                        'the advanced models; the economy models stay free.'
                    ),
                }

        # ── Check 2: lifetime cap (durable, a hard paywall) ──
        used_lifetime = await _lifetime_used(uid)
        if used_lifetime is not None and used_lifetime >= lifetime_limit:
            return {
                'code': 'free_lifetime_exhausted',
                'model': models[0] if models else '',
                'retry_after_seconds': 0,
                'message': (
                    f'سقف {_to_fa(lifetime_limit)} پیام رایگان شما به پایان رسیده '
                    'است. برای ادامهٔ گفتگو لطفاً حساب خود را شارژ کنید یا یک بستهٔ '
                    'پیام تهیه کنید.'
                ),
                'message_en': (
                    f'You have used all {lifetime_limit:,} of your free messages. '
                    'Top up your account or buy a message package to carry on.'
                ),
            }

        # ── Check 3: hourly cap (Redis, resets) ──
        hkey = _hourly_key(uid)
        raw = await rds.get(hkey)
        used_hour = int(raw) if raw is not None else 0
        if used_hour >= hourly_limit:
            ttl = await rds.ttl(hkey)
            if ttl is None or ttl < 0:
                # At the cap with no TTL -- can't give an honest countdown and
                # the bucket would never reset, so fail open rather than trap.
                logger.warning(f"free_tier: uid={uid} hourly at cap with no TTL, failing open")
                return None
            return {
                'code': 'free_hourly_throttle',
                'model': models[0] if models else '',
                'retry_after_seconds': int(ttl),
                'message': (
                    f'سقف {_to_fa(hourly_limit)} پیام در ساعت برای حساب رایگان پر '
                    f'شده است. حدود {_fa_duration(int(ttl))} دیگر می‌توانید ادامه '
                    'دهید، یا با شارژ حساب این محدودیت برداشته می‌شود.'
                ),
                # The countdown uses seconds rather than _fa_duration's Persian
                # words -- the same number, spelled for the other reader.
                'message_en': (
                    f'You have hit the free-account limit of {hourly_limit:,} messages '
                    f'per hour. You can continue in about {max(1, int(ttl) // 60)} minute(s), '
                    'or top up to remove the limit.'
                ),
            }

        # ── All three passed: consume one message ──
        # Durable lifetime counter first (the paywall must not be lost), then
        # the hourly Redis bucket.
        await _lifetime_incr(uid)

        new_hour = await rds.incr(hkey)
        if new_hour == 1:
            await rds.expire(hkey, HOURLY_WINDOW_SECONDS)
        else:
            ttl = await rds.ttl(hkey)
            if ttl is None or ttl < 0:
                await rds.expire(hkey, HOURLY_WINDOW_SECONDS)

        return None
    except Exception as e:
        logger.warning(f"free_tier.check_and_consume failed uid={uid} models={models}: {e}")
        return None


async def get_status(uid: int) -> dict:
    """Free-tier usage snapshot for GET /free-tier/status. Fails open to a
    'not limited' shape rather than raising, so a hiccup never breaks the
    wallet page."""
    try:
        if await has_paid(uid) or await has_balance(uid):
            return {'free_mode': False}

        cfg = await get_config()
        hourly_limit = int(cfg['free_hourly_limit'])
        lifetime_limit = int(cfg['free_lifetime_limit'])

        used_lifetime = await _lifetime_used(uid) or 0
        raw = await rds.get(_hourly_key(uid))
        used_hour = int(raw) if raw is not None else 0
        ttl = await rds.ttl(_hourly_key(uid))
        reset_in = int(ttl) if (ttl is not None and ttl > 0) else 0

        return {
            'free_mode': True,
            'hourly_limit': hourly_limit,
            'hourly_used': used_hour,
            'hourly_remaining': max(hourly_limit - used_hour, 0),
            'hourly_reset_in_seconds': reset_in,
            'lifetime_limit': lifetime_limit,
            'lifetime_used': used_lifetime,
            'lifetime_remaining': max(lifetime_limit - used_lifetime, 0),
            'max_input_per_million': int(cfg['free_tier_max_input_per_million']),
        }
    except Exception as e:
        logger.warning(f"free_tier.get_status failed uid={uid}: {e}")
        return {'free_mode': True}
